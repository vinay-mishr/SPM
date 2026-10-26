"""Party Master business logic (old software's cust_mst). Views stay thin and call these."""
import re

from django.conf import settings
from django.core.cache import cache
from django.db import connections, transaction

from config.legacy import fill_blank_columns, tables_using

from .choices import STATES
from .models import Party

GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GST_CATEGORY_CODES = {"REGULAR": "01", "UNREGISTERED": "03"}  # as stored in cust_mst.cat_cd
LOOKUP_TTL = 300  # seconds


class PartyInUseError(Exception):
    """Raised when a party can't be deleted (transactions or other records exist)."""


class PartyWriteDisabledError(Exception):
    """Raised when writing to the old software's database is switched off."""


class PartyCodeError(Exception):
    """Raised when no free party code is left for a letter."""


def legacy_enabled():
    """True when the SP_MACHINE database is connected (parties live in its cust_mst)."""
    return "legacy" in settings.DATABASES


def writes_enabled():
    return not legacy_enabled() or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise PartyWriteDisabledError("Saving to the SP_MACHINE database is switched off.")


def _db():
    return Party.objects.db


def _query(sql, params=None):
    with connections[_db()].cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.fetchall()


# --- Company settings ------------------------------------------------------------

def company_state_code():
    """GST state code of the company itself; decides Within (W) vs Interstate (I)."""
    return getattr(settings, "COMPANY_STATE_CODE", "03")


def default_supply_type(gst_state_code):
    if not gst_state_code:
        return "W"
    return "W" if gst_state_code == company_state_code() else "I"


# --- Lookups from the old software's master tables ------------------------------------

def states():
    """[{gcode, gst_code, name}] from gstate (built-in list when not connected),
    sorted by GST state code ascending (blank codes last)."""
    def load():
        if not legacy_enabled():
            rows = [{"gcode": code, "gst_code": code, "name": name.upper()} for code, name in STATES]
        else:
            raw = _query("SELECT [gcode], [gname], [stname] FROM [gstate]")
            rows = [
                {"gcode": g.strip(), "gst_code": (c or "").strip(), "name": (n or "").strip()}
                for g, c, n in raw
                if (n or "").strip(" .")  # skip placeholder rows such as "...."
            ]
        rows.sort(key=lambda s: (int(s["gst_code"]) if s["gst_code"].isdigit() else 999, s["name"]))
        return rows
    return cache.get_or_set(f"parties:states:{_db()}", load, LOOKUP_TTL)


def states_by_gcode():
    return {s["gcode"]: s for s in states()}


def gcode_for_gst_state(gst_code):
    """gstate code for a 2-digit GST state code (e.g. '03' -> '0003')."""
    return next((s["gcode"] for s in states() if s["gst_code"] == gst_code), "")


def _code_list(sql):
    def load():
        if not legacy_enabled():
            return []
        return [((c or "").strip(), (n or "").strip()) for c, n in _query(sql)]
    return load


def mkt_managers():
    """[(mcode, mname)] from mm_mst."""
    return cache.get_or_set(f"parties:mm:{_db()}", _code_list("SELECT [mcode], [mname] FROM [mm_mst] ORDER BY [mcode]"), LOOKUP_TTL)


def reps():
    """[(rcode, rname)] from rep_mst."""
    return cache.get_or_set(f"parties:rep:{_db()}", _code_list("SELECT [rcode], [rname] FROM [rep_mst] ORDER BY [rcode]"), LOOKUP_TTL)


def suggestions():
    """Distinct values already used, offered as type-ahead suggestions in the form."""
    result = {}
    for field in ("city", "transport", "association"):
        values = Party.objects.exclude(**{f"{field}__isnull": True}).values_list(field, flat=True).distinct()
        result[field] = sorted({v.strip() for v in values if v and v.strip() not in ("", ".")}, key=str.lower)
    return result


# --- Validation helpers -------------------------------------------------------------

def gstin_check_digit(first_14):
    """GSTIN checksum (last character), as published by GSTN."""
    total = 0
    for index, char in enumerate(first_14):
        product = GSTIN_CHARS.index(char) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36
    return GSTIN_CHARS[(36 - total % 36) % 36]


def gstin_error(gstin):
    """Return an error message for an invalid GSTIN, or '' when it is valid."""
    if len(gstin) != 15:
        return "GST no. must be exactly 15 characters."
    if not GSTIN_PATTERN.match(gstin):
        return "GST no. format is invalid (e.g. 03ABCDE1234F1Z5)."
    if gstin_check_digit(gstin[:14]) != gstin[14]:
        return "GST no. check digit is wrong — please re-check the number."
    return ""


class GstinLookupError(Exception):
    """Raised when the GSTIN is invalid or the provider has nothing for it --
    never silently returns an empty/fabricated result."""


def lookup_gstin_details(gstin):
    """Fetches registered business details for a GSTIN from the configured GST
    provider (apps.eway_bill.provider.lookup_gstin() -- the one endpoint in
    that integration that's actually been live-confirmed, see its own
    docstring) and maps only the fields it actually returns onto this form's
    own field names. Never invents a value: a key the response doesn't carry
    is simply left out of the result, and the caller (the Customer Master
    form) only fills in fields that are still blank.
    """
    gstin = (gstin or "").replace(" ", "").upper()
    error = gstin_error(gstin)
    if error:
        raise GstinLookupError(error)

    from apps.eway_bill.provider import ProviderError, lookup_gstin
    try:
        data = lookup_gstin(gstin)
    except ProviderError as exc:
        raise GstinLookupError(str(exc)) from exc

    # Real field names, confirmed live (2026-10-21) against this provider:
    # {Gstin, TradeName, LegalName, AddrBnm, AddrBno, AddrFlno, AddrSt,
    # AddrLoc, StateCode (int), AddrPncd (int), TxpType, Status, BlkStatus,
    # DtReg, DtDReg} -- a flat dict, no nested address object.
    def first(*keys):
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    result = {}
    name = first("TradeName", "LegalName")
    if name:
        result["name"] = name.upper()

    bno = first("AddrBno")
    bnm = first("AddrBnm")
    flno = first("AddrFlno")
    st = first("AddrSt")
    loc = first("AddrLoc")
    line_1 = ", ".join(p for p in [flno, bno, bnm] if p)
    line_2 = ", ".join(p for p in [st, loc] if p)
    if line_1:
        result["address_1"] = line_1[:50]
    if line_2:
        result["address_2"] = line_2[:50]
    # No separate city/town field in this provider's response -- AddrLoc is
    # the closest (a locality/phase, not necessarily a city name), already
    # folded into address_2 above rather than mislabelled as "city".

    pin = first("AddrPncd")
    if pin and re.fullmatch(r"\d{6}", pin):
        result["pin"] = pin

    gst_state_code = gstin[:2]
    gcode = gcode_for_gst_state(gst_state_code)
    if gcode:
        result["state_code"] = gcode

    return result


def normalize_mobile(value):
    """Strip spaces, dashes and a leading +91 / 91 / 0; return the remaining digits."""
    digits = re.sub(r"[\s\-()]", "", value or "")
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


# --- Codes ---------------------------------------------------------------------------

def next_party_code(name):
    """
    Old software's rule: first character of the name + the next 3-digit number for
    that character (e.g. the next 'A' party after A058 is A059).
    """
    first = (name or "").strip()[:1].upper()
    letter = first if first.isalnum() else "0"
    codes = Party.objects.filter(party_code__startswith=letter).values_list("party_code", flat=True)
    numbers = [int(c[1:]) for c in codes if c and len(c) == 4 and c[1:].isdigit()]
    number = max(numbers, default=0) + 1
    if number > 999:
        raise PartyCodeError(f"No free party code left for '{letter}' (all {letter}001-{letter}999 are used).")
    return f"{letter}{number:03d}"


# --- CRUD ------------------------------------------------------------------------------

def _apply(party, data, original=None):
    """Copy validated form data onto the cust_mst columns (plus the copied names)."""
    original = original or {}
    party.name = data["name"]
    party.group_code = settings.PARTY_DEBTOR_CODE if data["party_type"] == "SD" else settings.PARTY_CREDITOR_CODE
    party.address_1 = data["address_1"]
    party.address_2 = data["address_2"]
    party.address_3 = data["address_3"]
    party.city = data["city"]
    party.pin = data["pin"]

    state = states_by_gcode().get(data["state_code"])
    if state:
        party.state_gcode, party.state_gst_code, party.state_name = state["gcode"], state["gst_code"], state["name"]
    elif data["state_code"] != (party.state_gcode or "").strip():
        # State cleared (an unchanged, unlisted old value is kept as it is).
        party.state_gcode = party.state_gst_code = party.state_name = ""

    party.gst_no = data["gst_no"]
    party.gst_category = data["gst_category"] or ""
    party.gst_category_code = GST_CATEGORY_CODES.get(party.gst_category, party.gst_category_code or "")

    party.contact_person_1 = data["contact_person_1"]
    party.mobile_1 = data["mobile_1"]
    party.contact_person_2 = data["contact_person_2"]
    party.mobile_2 = data["mobile_2"]
    party.email = data["email"]
    party.transport = data["transport"]
    party.credit_days = data["credit_days"] or 0
    party.association = data["association"]
    party.supply_type = data["supply_type"] or default_supply_type(party.state_gst_code)
    party.permit = "Y" if data["permit"] else "N"

    # Keep the old active flag ('A', 'Y' or blank) when the party stays active.
    old_active = (party.active or "").strip().upper()
    if data["is_active"]:
        party.active = old_active if old_active != "N" and original else "Y"
    else:
        party.active = "N"

    managers = dict(mkt_managers())
    party.mkt_manager_code = data["mkt_manager"]
    party.mkt_manager_name = managers.get(data["mkt_manager"], party.mkt_manager_name or "")
    rep_names = dict(reps())
    party.rep_code = data["rep_code"]
    party.rep_name = rep_names.get(data["rep_code"], party.rep_name or "")
    return party


def create_party(form, username=""):
    """Insert a new party into cust_mst with the next code for its first letter."""
    _require_writes()
    db = _db()
    with transaction.atomic(using=db):
        party = _apply(Party(), form.cleaned_data)
        party.party_code = next_party_code(party.name)
        if Party.objects.filter(party_code=party.party_code).exists():
            raise PartyCodeError(f"Party code {party.party_code} already exists. Please try again.")
        party.save(force_insert=True)
        fill_blank_columns(db, Party._meta.db_table, "ccode", party.party_code, username)
    return party


def update_party(party, form):
    """Save changes to the same cust_mst row. The party code never changes."""
    _require_writes()
    _apply(party, form.cleaned_data, original=form.original)
    party.save(force_update=True)
    return party


def has_transactions(party):
    """Old rule: SELECT trans / SEEK party -> 'Transactions Exist'. trans.tcode + trans.tccode."""
    if connections[_db()].vendor != "microsoft":
        return False
    return bool(_query(
        "SELECT TOP 1 1 FROM [trans] WHERE [tcode] = %s AND [tccode] = %s",
        [party.group_code or "", party.party_code],
    ))


def delete_party(party):
    """Delete a party only when it has no transactions and isn't used elsewhere."""
    _require_writes()
    if has_transactions(party):
        raise PartyInUseError("Transactions Exist — this party cannot be deleted.")
    used_in = tables_using(_db(), settings.PARTY_USAGE_TABLES, party.party_code)
    if used_in:
        raise PartyInUseError(
            f"Party {party.party_code} cannot be deleted because it is used in: {', '.join(used_in)}."
        )
    party.delete()


# --- Serialisation ------------------------------------------------------------------------

def _clean(value):
    if isinstance(value, str) or value is None:
        value = (value or "").strip()
        return "" if value == "." else value
    return value


def serialize_party(party):
    group = _clean(party.group_code)
    if group == settings.PARTY_DEBTOR_CODE:
        party_type = "SD"
    elif group == settings.PARTY_CREDITOR_CODE:
        party_type = "SC"
    else:
        party_type = ""
    return {
        "id": party.party_code,
        "party_code": _clean(party.party_code) or party.party_code,
        "group_code": group,
        "name": _clean(party.name),
        "party_type": party_type,
        "address_1": _clean(party.address_1),
        "address_2": _clean(party.address_2),
        "address_3": _clean(party.address_3),
        "city": _clean(party.city),
        "pin": _clean(party.pin),
        "state_code": _clean(party.state_gcode),
        "state_gst_code": _clean(party.state_gst_code),
        "state_name": _clean(party.state_name).title(),
        "mkt_manager": _clean(party.mkt_manager_code),
        "mkt_manager_name": _clean(party.mkt_manager_name),
        "rep_code": _clean(party.rep_code),
        "rep_name": _clean(party.rep_name),
        "gst_no": _clean(party.gst_no),
        "gst_category": _clean(party.gst_category).upper(),
        "contact_person_1": _clean(party.contact_person_1),
        "phone_1": _clean(party.phone_1),
        "mobile_1": _clean(party.mobile_1),
        "contact_person_2": _clean(party.contact_person_2),
        "phone_2": _clean(party.phone_2),
        "mobile_2": _clean(party.mobile_2),
        "email": _clean(party.email),
        "transport": _clean(party.transport),
        "credit_days": int(party.credit_days or 0),
        "is_active": party.is_active,
        "association": _clean(party.association),
        "supply_type": _clean(party.supply_type) if _clean(party.supply_type) in ("W", "I") else "",
        "permit": _clean(party.permit).upper() == "Y",
    }


def list_parties():
    """All parties sorted by name (as the old list: SET ORDER TO cname)."""
    return [serialize_party(p) for p in Party.objects.order_by("name")]

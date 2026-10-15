"""
Vendor Master business logic. Old VFP form ``supfrm``: cust_mst rows with
``code = PSCCODE`` (the Sundry Creditor group, ``settings.PARTY_CREDITOR_CODE``
/ "S002"). No new table: this is a thin, creditor-only layer over
apps.parties (the existing cust_mst / Party model), so Party Master, Vendor
Master and the database always agree on the same rows.

Field mapping used by the Vendor form (all real cust_mst columns, reusing the
names already defined on apps.parties.models.Party):
    Phone No.          -> phone_1        (cphno)
    Mobile              -> mobile_1       (mobile)
    Contact Person 1     -> contact_person_1 (ccper)
    Mobile No. (person 1) -> phone_2       (cphno1)
    Con. Person 2        -> contact_person_2 (ccper1)
    Mobile No. (person 2) -> mobile_2       (mobile1)
    Grade                -> grade          (grade)
"""
from django.conf import settings
from django.db import transaction

from apps.parties import services as party_services
from apps.parties.models import Party
from apps.parties.services import (  # re-exported for the views/forms
    PartyCodeError,
    PartyInUseError,
    PartyWriteDisabledError,
    company_state_code,
    gcode_for_gst_state,
    gstin_error,
    legacy_enabled,
    next_party_code,
    normalize_mobile,
    states,
    states_by_gcode,
    writes_enabled,
)

LOOKUP_TTL = party_services.LOOKUP_TTL


def _require_writes():
    if not writes_enabled():
        raise PartyWriteDisabledError("Saving to the SP_MACHINE database is switched off.")


def _db():
    return Party.objects.db


def _is_vendor(party):
    return (party.group_code or "").strip() == settings.PARTY_CREDITOR_CODE


def _clean(value):
    if isinstance(value, str) or value is None:
        value = (value or "").strip()
        return "" if value == "." else value
    return value


def suggestions():
    """Type-ahead suggestions, taken from vendor (creditor) records only."""
    result = {}
    qs = Party.objects.filter(group_code=settings.PARTY_CREDITOR_CODE)
    for field in ("city", "transport", "association"):
        values = qs.exclude(**{f"{field}__isnull": True}).values_list(field, flat=True).distinct()
        result[field] = sorted({v.strip() for v in values if v and v.strip() not in ("", ".")}, key=str.lower)
    return result


def serialize_vendor(party):
    state = party_services.serialize_party(party)
    state["grade"] = _clean(party.grade).upper()
    state["opening_balance"] = float(party.opening_balance or 0)
    # Renamed to match the Vendor form's field names (see the mapping above).
    state["phone_no"] = state.pop("phone_1")
    state["mobile_person_1"] = state.pop("phone_2")
    state["mobile_person_2"] = state.pop("mobile_2")
    return state


def list_vendors():
    """All Sundry Creditors, sorted by name (old rule: SET ORDER TO CNAME / SCAN FOR CODE=PSCCODE)."""
    qs = Party.objects.filter(group_code=settings.PARTY_CREDITOR_CODE).order_by("name")
    return [serialize_vendor(p) for p in qs]


def get_vendor(pk):
    """A vendor by party code, or None if it isn't a Sundry Creditor row."""
    party = Party.objects.filter(pk=pk).first()
    if party is None or not _is_vendor(party):
        return None
    return party


def _apply(party, data, original=None):
    original = original or {}
    party.name = data["name"]
    party.group_code = settings.PARTY_CREDITOR_CODE
    party.address_1 = data["address_1"]
    party.address_2 = data["address_2"]
    party.address_3 = data["address_3"]
    party.city = data["city"].upper()
    party.pin = data["pin"]

    state = states_by_gcode().get(data["state_code"])
    if state:
        party.state_gcode, party.state_gst_code, party.state_name = state["gcode"], state["gst_code"], state["name"]
    elif data["state_code"] != (party.state_gcode or "").strip():
        party.state_gcode = party.state_gst_code = party.state_name = ""

    party.gst_no = data["gst_no"]
    party.gst_category = data["gst_category"] or ""
    party.gst_category_code = party_services.GST_CATEGORY_CODES.get(
        party.gst_category, party.gst_category_code or ""
    )

    party.mobile_1 = data["mobile_1"]
    party.contact_person_1 = data["contact_person_1"]
    party.phone_2 = data["mobile_person_1"]
    party.contact_person_2 = data["contact_person_2"]
    party.mobile_2 = data["mobile_person_2"]
    party.email = data["email"]

    party.opening_balance = data["opening_balance"] or 0
    party.transport = data["transport"]
    party.credit_days = data["credit_days"] or 0
    party.association = data["association"]
    party.grade = data["grade"]
    party.supply_type = data["supply_type"] or party_services.default_supply_type(party.state_gst_code)

    old_active = (party.active or "").strip().upper()
    if data["is_active"]:
        party.active = old_active if old_active != "N" and original else "Y"
    else:
        party.active = "N"
    return party


def create_vendor(form, username=""):
    """Insert a new Sundry Creditor into cust_mst with the next free code."""
    _require_writes()
    db = _db()
    with transaction.atomic(using=db):
        party = _apply(Party(), form.cleaned_data)
        party.party_code = next_party_code(party.name)
        if Party.objects.filter(party_code=party.party_code).exists():
            raise PartyCodeError(f"Vendor code {party.party_code} already exists. Please try again.")
        party.save(force_insert=True)
        from config.legacy import fill_blank_columns
        fill_blank_columns(db, Party._meta.db_table, "ccode", party.party_code, username)
    return party


def update_vendor(party, form):
    _require_writes()
    _apply(party, form.cleaned_data, original=form.original)
    party.save(force_update=True)
    return party


def delete_vendor(party):
    _require_writes()
    if party_services.has_transactions(party):
        raise PartyInUseError("Transactions Exist — this vendor cannot be deleted.")
    used_in = party_services.tables_using(_db(), settings.PARTY_USAGE_TABLES, party.party_code)
    if used_in:
        raise PartyInUseError(
            f"Vendor {party.party_code} cannot be deleted because it is used in: {', '.join(used_in)}."
        )
    party.delete()

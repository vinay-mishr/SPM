"""
Quotation (Spare Part) services -- listing, loading, saving and deleting quotations on
the old software's shared quot_mst / quot_dat tables, following the legacy VFP QUOT4
form (and its QUOTATION list filtered ``TYPE='Q'``):

* Numbering: SAME shared counter as apps.quotations, ``inv_no.quot_no`` + 1 (never
  below the highest number already used across BOTH screens -- quot_no is quot_mst's
  single primary key, so numbers can never collide between the two types).
* Save (add): duplicate check over ALL quot_mst rows (shared numbers), insert header +
  lines, bump the counter -- one transaction.
* Save (modify): update the header and replace this quotation's quot_dat lines, in one
  transaction.
* Only rows whose ``type = 'Q'`` are read or written here; blank-type rows belong to
  apps.quotations and are never touched.
* Items come from part-mst (apps.parts.models.Part), not the item master.

Every amount is recomputed with apps.quotations.calc (shared formulas -- see that
module's docstring for the exact rules); the browser's totals are never trusted.
"""
from datetime import date, datetime

from django.conf import settings
from django.db import connections, router, transaction
from django.db.models import Q
from django.utils import timezone

from apps.parts.models import Part
from apps.quotations import calc
from apps.quotations.models import QuotationHeader, QuotationMeta
from apps.quotations.services import new_token, run_once  # fully generic, no business logic of their own; re-exported for views.py

from config.legacy import fill_blank_columns

LINES_TABLE = "quot_dat"
HEADER_TABLE = "quot_mst"
QUOT_TYPE = "Q"  # what the legacy QUOT4 form writes into quot_mst.type / quot_dat.type
PAGE_SIZE = 50

MAX_QTY = calc.Decimal("9999999.999")
MAX_RATE = calc.Decimal("99999999.99")
MAX_LINE_AMOUNT = calc.Decimal("9999999999.99")
MAX_LINE_DISCOUNT = calc.Decimal("99999999.99")
MAX_LINE_GST = calc.Decimal("99999999.99")
MAX_TOTAL = calc.Decimal("9999999999.99")
MAX_DISCOUNT = calc.Decimal("99999999.99")
MAX_GST = calc.Decimal("999999.99")
MAX_NET = calc.Decimal("99999999.99")
MAX_PARTICULAR = 8000

_OWNED = Q(quot_type=QUOT_TYPE)
_LINE_OWNED_SQL = "LTRIM(RTRIM(type)) = %s"


class QuotationSparepartError(Exception):
    def __init__(self, message, errors=None, status=400):
        super().__init__(message)
        self.errors = errors or {}
        self.status = status


# --- helpers -----------------------------------------------------------------------------

def legacy_alias():
    return router.db_for_write(QuotationHeader) or "default"


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _is_sql_server(alias):
    return connections[alias].vendor == "microsoft"


def _rows(alias, sql, params=None):
    with connections[alias].cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exec(alias, sql, params=None):
    with connections[alias].cursor() as cur:
        cur.execute(sql, params or [])


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _money(value):
    return f"{calc.q2(value or 0):.2f}"


def _qty(value):
    return f"{calc.Decimal(value or 0).quantize(calc.Q3):.3f}"


def parse_date(value):
    value = (value or "").strip() if isinstance(value, str) else value
    if not value:
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def normalise_no(value):
    value = (value or "").strip() if isinstance(value, str) else str(value or "")
    if not value.isdigit() or len(value) > 6:
        return None
    return str(int(value)) if int(value) > 0 else None


def default_terms():
    terms = list(settings.QUOTATION_DEFAULT_TERMS)[:5]
    return terms + [""] * (5 - len(terms))


def default_bank_lines():
    bank = settings.QUOTATION_BANK
    return [
        f"BANK NAME : {bank['name']}",
        f"A/C NO : {bank['account_no']}",
        f"IFSC CODE : {bank['ifsc']}",
        f"BRANCH : {bank['branch']}",
    ]


def availability(stock, qty):
    """Legacy AVAIL flag: NA = no stock, A = enough for the qty, PA = partly available."""
    if stock is None or calc.Decimal(stock) <= 0:
        return "NA"
    return "A" if calc.Decimal(stock) >= qty else "PA"


# --- numbering (shared with apps.quotations) ----------------------------------------------

def _highest_no(alias):
    nums = [int(n.strip()) for n in QuotationHeader.objects.using(alias).values_list("quot_no", flat=True)
            if n and n.strip().isdigit()]
    return max(nums) if nums else 0


def _counter(alias, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock and _is_sql_server(alias) else ""
    rows = _rows(alias, f"SELECT quot_no FROM inv_no{hint}")
    if not rows:
        return None
    return int(rows[0]["quot_no"] or 0)


def next_no():
    alias = legacy_alias()
    return str(max(_counter(alias) or 0, _highest_no(alias)) + 1)


def _number_taken(alias, quot_no):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if _is_sql_server(alias) else ""
    return bool(_rows(alias, f"SELECT quot_no FROM {HEADER_TABLE}{hint} WHERE quot_no = %s", [quot_no]))


# --- masters -----------------------------------------------------------------------------

def search_parties(term, limit=100):
    from apps.parties.models import Party

    term = (term or "").strip()
    qs = Party.objects.all()
    if term:
        qs = qs.filter(Q(name__icontains=term) | Q(party_code__istartswith=term))
    return [
        {"code": c, "name": _clean(n), "city": _clean(ct), "phone": _clean(p) or _clean(m)}
        for c, n, ct, p, m in qs.order_by("name").values_list("party_code", "name", "city", "phone_1", "mobile_1")[:limit]
    ]


def search_items(term, limit=100):
    term = (term or "").strip()
    qs = Part.objects.all()
    if term:
        qs = qs.filter(Q(description_1__icontains=term) | Q(part_number__istartswith=term))
    return [
        {"code": c, "name": _clean(n), "unit": _clean(u), "gst_percent": f"{(g or 0):.2f}",
         "rate": f"{(r or 0):.2f}", "stock": f"{(s or 0):.0f}"}
        for c, n, u, g, r, s in qs.order_by("part_number").values_list(
            "part_number", "description_1", "unit", "gst_percent", "sale_rate", "current_stock")[:limit]
    ]


# --- listing -----------------------------------------------------------------------------

def _sort_key(row):
    no = row["quot_no"]
    return (row["date"] or "", int(no) if no.isdigit() else -1, no)


def list_quotations(start, end, search=""):
    qs = QuotationHeader.objects.filter(_OWNED)
    if start:
        qs = qs.filter(quot_date__gte=start)
    if end:
        qs = qs.filter(quot_date__lte=end)
    headers = list(qs.values("quot_no", "quot_date", "party_code", "party_name", "city", "description", "subject", "net_amount"))
    confirmed = dict(QuotationMeta.objects.filter(
        quot_no__in=[_clean(h["quot_no"]) for h in headers], confirmed_at__isnull=False,
    ).values_list("quot_no", "confirmed_at"))
    first_items = _first_item_names([_clean(h["quot_no"]) for h in headers])
    term = (search or "").strip().lower()
    rows = []
    for h in headers:
        no = _clean(h["quot_no"])
        party = _clean(h["party_name"])
        if term and term not in no.lower() and term not in party.lower():
            continue
        rows.append({
            "quot_no": no,
            "date": h["quot_date"].isoformat() if h["quot_date"] else "",
            "party": party,
            "city": _clean(h["city"]),
            "description": _clean(h["description"]) or _clean(h["subject"]) or first_items.get(no, ""),
            "net_amount": _money(h["net_amount"]),
            "confirmed": no in confirmed,
        })
    rows.sort(key=_sort_key, reverse=True)
    return rows


def _first_item_names(quot_nos):
    if not quot_nos:
        return {}
    alias = legacy_alias()
    quot_nos, rows = list(quot_nos), []
    for i in range(0, len(quot_nos), 500):
        chunk = quot_nos[i:i + 500]
        marks = ", ".join(["%s"] * len(chunk))
        rows += _rows(alias, f"SELECT quot_no, i_code FROM {LINES_TABLE} WHERE quot_no IN ({marks}) AND {_LINE_OWNED_SQL}",
                      chunk + [QUOT_TYPE])
    codes = {}
    for r in rows:
        codes.setdefault(_clean(r["quot_no"]), []).append(_clean(r["i_code"]))
    names = dict(Part.objects.filter(part_number__in={c for cs in codes.values() for c in cs})
                 .values_list("part_number", "description_1"))
    result = {}
    for no, cs in codes.items():
        first = _clean(names.get(cs[0])) or cs[0]
        result[no] = first + (f" (+{len(cs) - 1} more)" if len(cs) > 1 else "")
    return result


# --- one quotation -----------------------------------------------------------------------

def _load_lines(alias, quot_no):
    return _rows(
        alias,
        f"SELECT i_code, unit, qty, rate, amount, dis, dis_amt, vat, vat_amt, av, particular "
        f"FROM {LINES_TABLE} WHERE quot_no = %s AND {_LINE_OWNED_SQL}",
        [quot_no, QUOT_TYPE],
    )


def get_quotation(quot_no):
    from apps.parties.models import Party

    no = normalise_no(quot_no)
    if not no:
        return None
    header = QuotationHeader.objects.filter(_OWNED, quot_no=no).first()
    if not header:
        return None
    alias = legacy_alias()
    gst_applicable = (_clean(header.gst_applicable) or "Y").upper() != "N"
    raw_lines = _load_lines(alias, no)
    masters = {p.part_number: p for p in Part.objects.filter(
        part_number__in={_clean(l["i_code"]) for l in raw_lines})}
    lines = []
    for n, l in enumerate(raw_lines, start=1):
        code = _clean(l["i_code"])
        part = masters.get(code)
        disc_pct, disc_amt = l["dis"] or 0, l["dis_amt"] or 0
        gross = calc.q2(calc.Decimal(l["qty"] or 0) * calc.Decimal(l["rate"] or 0))
        if disc_amt and calc.q2(gross * calc.Decimal(disc_pct) / calc.HUNDRED) != calc.q2(disc_amt):
            disc_pct = 0  # the discount was entered as an amount (its % is only derived)
        amounts = calc.calc_line(l["qty"] or 0, l["rate"] or 0, disc_pct, disc_amt, l["vat"] or 0, gst_applicable)
        lines.append({
            "sno": n, "item_code": code,
            "item_name": _clean(part.description_1) if part else "(not in Part Master)",
            "unit": _clean(l["unit"]),
            "qty": _qty(l["qty"]), "rate": _money(l["rate"]),
            "disc_pct": _money(disc_pct), "disc_pct_effective": _money(amounts["disc_pct"]),
            "disc_amt": _money(amounts["discount"]),
            "gst_pct": _money(l["vat"]), "gst_amt": _money(amounts["gst"]),
            "amount": _money(amounts["gross"]), "taxable": _money(amounts["taxable"]),
            "line_total": _money(amounts["total"]),
            "availability": _clean(l["av"]), "particular": (l["particular"] or "").rstrip(),
        })
    meta = QuotationMeta.objects.filter(quot_no=no).first()
    terms = [_clean(getattr(header, f"term_{i}")) for i in range(1, 6)]
    bank = [_clean(getattr(header, f"bank_{i}")) for i in range(1, 5)]
    party = Party.objects.filter(party_code=_clean(header.party_code)).first() if _clean(header.party_code) else None
    address = [_clean(getattr(party, f, "")) for f in ("address_1", "address_2", "address_3", "city")] if party else []
    return {
        "quot_no": no,
        "quot_date": header.quot_date.isoformat() if header.quot_date else "",
        "ref_no": _clean(header.ref_no),
        "ref_date": header.ref_date.isoformat() if header.ref_date else "",
        "party_code": _clean(header.party_code),
        "party_name": _clean(header.party_name),
        "party_address": [a for a in address if a and a != "."],
        "party_gstin": _clean(party.gst_no) if party else "",
        "city": _clean(header.city),
        "phone": _clean(header.phone),
        "kind_attention": [_clean(header.kind_attention_1), _clean(header.kind_attention_2), _clean(header.kind_attention_3)],
        "gst_applicable": "Y" if gst_applicable else "N",
        "remarks": (header.remarks or "").rstrip(),
        "terms": terms,
        "bank": bank,
        "items": lines,
        "total_amount": _money(header.amount),
        "discount_amount": _money(header.discount_amount),
        "gst_amount": _money(header.gst_amount),
        "net_amount": _money(header.net_amount),
        "confirmed": bool(meta and meta.confirmed_at),
        "confirmed_by": _clean(meta.confirmed_by) if meta else "",
        "confirmed_at": meta.confirmed_at.strftime("%d/%m/%Y %H:%M") if meta and meta.confirmed_at else "",
    }


def blank_quotation():
    return {
        "quot_no": next_no(), "quot_date": date.today().isoformat(), "ref_no": "", "ref_date": "",
        "party_code": "", "party_name": "", "city": "", "phone": "", "kind_attention": ["", "", ""],
        "gst_applicable": "Y", "remarks": "",
        "terms": default_terms(), "bank": default_bank_lines(), "items": [],
        "total_amount": "0.00", "discount_amount": "0.00", "gst_amount": "0.00", "net_amount": "0.00",
        "confirmed": False, "confirmed_by": "", "confirmed_at": "",
    }


# --- validation --------------------------------------------------------------------------

_TEXT_LIMITS = {"ref_no": ("Reference no.", 10), "city": ("City", 30), "phone": ("Phone no.", 20)}


def _text(payload, key):
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _decimal_places(value):
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _clean_line(n, raw, parts, gst_applicable):
    def fail(message):
        raise QuotationSparepartError(f"Row {n}: {message}", {"items": f"Row {n}: {message}"})

    if not isinstance(raw, dict):
        fail("invalid item.")
    code = (str(raw.get("item_code") or "")).strip().upper()
    if not code:
        fail("select a part.")
    part = parts.get(code)
    if not part:
        fail(f"part '{code}' isn't in the Part Master.")
    try:
        qty = calc.to_decimal(raw.get("qty"), "Quantity")
        rate = calc.to_decimal(raw.get("rate"), "Rate")
        disc_pct = calc.to_decimal(raw.get("disc_pct"), "Discount %")
        disc_amt = calc.to_decimal(raw.get("disc_amt"), "Discount amount")
        gst_pct = calc.to_decimal(raw.get("gst_pct"), "GST %")
    except calc.CalcError as exc:
        fail(str(exc))
    if qty <= 0:
        fail("quantity must be more than 0.")
    if qty > MAX_QTY or _decimal_places(qty) > 3:
        fail("quantity must be at most 9,999,999.999 with up to 3 decimals.")
    if rate < 0:
        fail("rate can't be negative.")
    if rate > MAX_RATE or _decimal_places(rate) > 2:
        fail("rate must be at most 99,999,999.99 with up to 2 decimals.")
    if not (0 <= disc_pct <= 100) or _decimal_places(disc_pct) > 2:
        fail("discount % must be between 0 and 100.")
    if disc_amt < 0:
        fail("discount amount can't be negative.")
    if not (0 <= gst_pct <= 100) or _decimal_places(gst_pct) > 2:
        fail("GST % must be between 0 and 100.")
    amounts = calc.calc_line(qty, rate, disc_pct, disc_amt, gst_pct, gst_applicable)
    if amounts["gross"] > MAX_LINE_AMOUNT:
        fail("amount (qty x rate) is too large.")
    if amounts["discount"] > amounts["gross"]:
        fail("discount can't be more than the amount.")
    if amounts["discount"] > MAX_LINE_DISCOUNT or amounts["gst"] > MAX_LINE_GST:
        fail("discount / GST amount is too large.")
    particular = raw.get("particular") if isinstance(raw.get("particular"), str) else ""
    particular = particular.replace("\r\n", "\n").rstrip()
    if len(particular) > MAX_PARTICULAR:
        fail(f"particulars can be at most {MAX_PARTICULAR} characters.")
    return {
        "item_code": code, "unit": _clean(part.unit)[:3],
        "qty": qty, "rate": rate, "gst_pct": gst_pct, "particular": particular,
        "stock": part.current_stock, **amounts,
    }


def validate(payload):
    from apps.parties.models import Party

    if not isinstance(payload, dict):
        raise QuotationSparepartError("Invalid request.")
    errors = {}
    quot_no = normalise_no(payload.get("quot_no"))
    if not quot_no:
        errors["quot_no"] = "Quotation no. must be a number of up to 6 digits."
    quot_date = parse_date(payload.get("quot_date"))
    if not quot_date:
        errors["quot_date"] = "Enter a valid quotation date."
    ref_date = None
    if _text(payload, "ref_date"):
        ref_date = parse_date(payload.get("ref_date"))
        if not ref_date:
            errors["ref_date"] = "Enter a valid reference date."
    party_code = _text(payload, "party_code").upper()
    party = Party.objects.filter(party_code=party_code).first() if party_code else None
    if not party_code:
        errors["party_code"] = "Select a party from the Customer Master."
    elif not party:
        errors["party_code"] = "Party not found in the Customer Master."
    for key, (label, limit) in _TEXT_LIMITS.items():
        if len(_text(payload, key)) > limit:
            errors[key] = f"{label} can be at most {limit} characters."
    kind = payload.get("kind_attention") if isinstance(payload.get("kind_attention"), list) else []
    kind = [(k.strip() if isinstance(k, str) else "") for k in kind[:3]] + [""] * (3 - len(kind[:3]))
    if any(len(k) > 50 for k in kind):
        errors["kind_attention"] = "Each Kind Attention line can be at most 50 characters."
    terms = payload.get("terms") if isinstance(payload.get("terms"), list) else []
    terms = [(t.strip() if isinstance(t, str) else "") for t in terms[:5]] + [""] * (5 - len(terms[:5]))
    if any(len(t) > 80 for t in terms):
        errors["terms"] = "Each terms & conditions line can be at most 80 characters."
    bank = payload.get("bank") if isinstance(payload.get("bank"), list) else []
    bank = [(b.strip() if isinstance(b, str) else "") for b in bank[:4]] + [""] * (4 - len(bank[:4]))
    if any(len(b) > 40 for b in bank):
        errors["bank"] = "Each bank detail line can be at most 40 characters."
    remarks = payload.get("remarks") if isinstance(payload.get("remarks"), str) else ""
    remarks = remarks.replace("\r\n", "\n").rstrip()
    if len(remarks) > MAX_PARTICULAR:
        errors["remarks"] = f"Remarks can be at most {MAX_PARTICULAR} characters."
    gst_flag = _text(payload, "gst_applicable").upper() or "Y"
    if gst_flag not in ("Y", "N"):
        errors["gst_applicable"] = "GST must be Y or N."
    gst_applicable = gst_flag != "N"

    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if not raw_items:
        errors["items"] = "Add at least one item."
    if errors:
        raise QuotationSparepartError("Please correct the highlighted fields.", errors)

    codes = {str((r or {}).get("item_code") or "").strip().upper() for r in raw_items if isinstance(r, dict)}
    parts = {p.part_number.strip().upper(): p for p in Part.objects.filter(part_number__in=codes)}
    lines = [_clean_line(n, raw, parts, gst_applicable) for n, raw in enumerate(raw_items, start=1)]
    totals = calc.calc_totals(lines)
    for key, limit, label in (("total", MAX_TOTAL, "Total amount"), ("discount", MAX_DISCOUNT, "Discount amount"),
                              ("gst", MAX_GST, "GST amount"), ("net", MAX_NET, "Net amount")):
        if totals[key] > limit:
            raise QuotationSparepartError(f"{label} ({totals[key]:,.2f}) is more than the old software's column can hold "
                                 f"({limit:,.2f}). Split this into more than one quotation.", {"items": f"{label} too large."})
    return {
        "quot_no": quot_no, "quot_date": quot_date, "ref_no": _text(payload, "ref_no"), "ref_date": ref_date,
        "party": party, "city": _text(payload, "city"), "phone": _text(payload, "phone"),
        "kind": kind, "gst_flag": "Y" if gst_applicable else "N", "remarks": remarks, "terms": terms, "bank": bank,
        "lines": lines, "totals": totals,
    }


# --- save / delete ----------------------------------------------------------------------

def _header_fields(data, uname):
    party = data["party"]
    t = data["totals"]
    fields = {
        "quot_date": data["quot_date"], "party_code": party.party_code.strip()[:4],
        "party_name": _clean(party.name)[:50], "city": data["city"], "phone": data["phone"],
        "ref_no": data["ref_no"], "ref_date": data["ref_date"],
        "kind_attention_1": data["kind"][0], "kind_attention_2": data["kind"][1], "kind_attention_3": data["kind"][2],
        "gst_applicable": data["gst_flag"],
        "amount": t["total"], "discount_amount": t["discount"], "gst_amount": t["gst"], "net_amount": t["net"],
        "discount_rate": calc.ZERO, "surcharge_amount": calc.ZERO, "surcharge_rate": calc.ZERO,
        "remarks": data["remarks"], "uname": uname,
    }
    for i in range(5):
        fields[f"term_{i + 1}"] = data["terms"][i]
    for i in range(4):
        fields[f"bank_{i + 1}"] = data["bank"][i]
    return fields


def _insert_lines(alias, data, uname):
    party = data["party"]
    sql = (
        f"INSERT INTO {LINES_TABLE} (quot_no, quot_dt, p_code, i_code, qty, rate, amount, av, dis, vat, "
        "vat_amt, uname, dis_amt, party, unit, particular, yn, type) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    for l in data["lines"]:
        _exec(alias, sql, [
            data["quot_no"], data["quot_date"], party.party_code.strip()[:4], l["item_code"], l["qty"], l["rate"],
            l["gross"], availability(l["stock"], l["qty"]), l["disc_pct"], l["gst_pct"],
            l["gst"], uname, l["discount"], _clean(party.name)[:50], l["unit"], l["particular"],
            data["gst_flag"], QUOT_TYPE,
        ])


def _delete_lines(alias, quot_no):
    _exec(alias, f"DELETE FROM {LINES_TABLE} WHERE quot_no = %s AND {_LINE_OWNED_SQL}", [quot_no, QUOT_TYPE])


def _require_writes():
    if not writes_enabled():
        raise QuotationSparepartError("Saving to the SP_MACHINE database is switched off. Nothing was changed.", status=403)


def save_quotation(payload, key=None, user=None, confirm=False):
    _require_writes()
    adding = key is None
    data = validate(payload)
    no = data["quot_no"]
    uname = (user.get_username() if user else "")[:10]
    alias = legacy_alias()
    if not adding:
        key = normalise_no(key)
        if key != no:
            raise QuotationSparepartError("The quotation no. can't be changed on an existing quotation.", {"quot_no": "Quotation no. is fixed."})
    header = _header_fields(data, uname)

    with transaction.atomic(using=alias):
        if adding:
            counter = _counter(alias, lock=True)
            if _number_taken(alias, no):
                suggestion = max(counter or 0, _highest_no(alias)) + 1
                raise QuotationSparepartError(
                    f"Quotation No. {no} already exists. The next free number is {suggestion}.",
                    {"quot_no": "Quotation No. Already Exists."},
                )
            QuotationHeader.objects.using(alias).create(
                quot_no=no, div=settings.QUOTATION_DIV[:2], quot_type=QUOT_TYPE, **header)
            _insert_lines(alias, data, uname)
            if counter is not None and int(no) > counter:
                _exec(alias, "UPDATE inv_no SET quot_no = %s", [int(no)])
        else:
            existing = QuotationHeader.objects.using(alias).filter(quot_no=no).first()
            if not existing:
                raise QuotationSparepartError("This quotation no longer exists.", status=404)
            if (_clean(existing.quot_type) or "") != QUOT_TYPE:
                raise QuotationSparepartError("This quotation was made in the other quotation screen and can't be changed here.", status=403)
            QuotationHeader.objects.using(alias).filter(_OWNED, quot_no=no).update(**header)
            _delete_lines(alias, no)
            _insert_lines(alias, data, uname)
        fill_blank_columns(alias, HEADER_TABLE, "quot_no", no, uname=uname)
        fill_blank_columns(alias, LINES_TABLE, "quot_no", no, uname=uname)

        now = timezone.now()
        username = user.get_username() if user else ""
        meta = QuotationMeta.objects.using(alias).filter(quot_no=no).first()
        if meta is None or adding:
            if meta is not None:
                meta.delete()
            meta = QuotationMeta(quot_no=no, created_by=username, created_at=now)
        if not adding:
            meta.updated_by, meta.updated_at = username, now
        if confirm:
            meta.confirmed_by, meta.confirmed_at = username, now
        meta.save(using=alias)
    verb = "confirmed" if confirm else "saved"
    return {"quot_no": no, "message": f"Quotation {no} {verb}."}


def delete_quotation(quot_no):
    _require_writes()
    no = normalise_no(quot_no)
    alias = legacy_alias()
    with transaction.atomic(using=alias):
        counter = _counter(alias, lock=True)
        header = QuotationHeader.objects.using(alias).filter(quot_no=no).first() if no else None
        if not header:
            raise QuotationSparepartError("This quotation no longer exists.", status=404)
        if (_clean(header.quot_type) or "") != QUOT_TYPE:
            raise QuotationSparepartError("This quotation was made in the other quotation screen and can't be deleted here.", status=403)
        _delete_lines(alias, no)
        QuotationHeader.objects.using(alias).filter(_OWNED, quot_no=no).delete()
        if counter is not None and int(no) == counter:
            _exec(alias, "UPDATE inv_no SET quot_no = %s", [counter - 1])
        QuotationMeta.objects.using(alias).filter(quot_no=no).delete()
    return {"quot_no": no, "message": f"Quotation {no} deleted."}

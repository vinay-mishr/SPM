"""GST Credit Note Entry (item-based, VFP "gcre1" form)."""
from datetime import date as _date_cls, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from django.db.models import F

from apps.parties.models import Party
from apps.parts.models import Part

from .models import GcBillHeader, GMasterCreditLine, InvNo

DIV = "SP"
Q2 = Decimal("0.01")
RATE_BUCKETS = (5, 12, 18, 28)

# Real rows may have a blank bill_type on older data; new rows saved from this
# screen are always stamped 'C' -- mirrors apps.returnable_challan's own
# tolerant HEADER_TYPE filter for the same reason (never hide pre-existing data).
_HEADER_TYPE = Q(bill_type="C") | Q(bill_type="") | Q(bill_type__isnull=True)
_LINE_TYPE = _HEADER_TYPE


class CreditNoteError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _d(value):
    try:
        return Decimal(str(value or "0").strip() or "0")
    except InvalidOperation:
        return None


def _date(value):
    if isinstance(value, _date_cls):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _clean(v):
    return (v or "").strip() if isinstance(v, str) else v


def _money(v):
    return f"{(v or 0):.2f}"


def _first(qs):
    rows = list(qs[:1])
    return rows[0] if rows else None


def _adjust_stock(item_code, qty_delta):
    """A Credit Note is a sales return -- the goods physically come back, so
    saving a line must INCREASE stock (qty_delta > 0) and deleting/removing
    one must reverse that (qty_delta < 0). Mirrors apps.spare_invoice's own
    _adjust_stock against the same part-mst.cur_stk column (Part.current_stock
    here), just the opposite sign convention since that module consumes
    stock on save instead of returning it."""
    if not item_code:
        return
    Part.objects.filter(part_number=item_code).update(
        current_stock=F("current_stock") + qty_delta
    )


def _highest_no():
    nums = [int(n) for n in GcBillHeader.objects.filter(_HEADER_TYPE).values_list("bill_no", flat=True)
            if str(n).strip().isdigit()]
    return max(nums) if nums else 0


def next_cn_no():
    counter = _first(InvNo.objects.values_list("next_cn_no", flat=True))
    return str(max(int(counter) if counter is not None else 0, _highest_no()) + 1)


def _allocate_cn_no():
    counter = _first(InvNo.objects.select_for_update().values_list("next_cn_no", flat=True))
    new_no = max(int(counter) if counter is not None else 0, _highest_no()) + 1
    InvNo.objects.update(next_cn_no=new_no)
    return str(new_no)


def totals(lines, gst_pct, freight, freight_gst_pct, adj_amt1, adj_amt2):
    amount = Decimal("0")
    for ln in lines:
        base = ln["qty"] * ln["rate"]
        d = (base * ln["dis_pct"] / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
        ln["amount"] = (base - d).quantize(Q2, ROUND_HALF_UP)
        amount += ln["amount"]
    gst_amt = (amount * gst_pct / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
    freight_gst = (freight * freight_gst_pct / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
    net = (amount + gst_amt + freight + freight_gst + adj_amt1 + adj_amt2).quantize(Q2, ROUND_HALF_UP)
    return {"amount": amount, "gst_amt": gst_amt, "freight_gst": freight_gst, "net": net}


def _validate(payload):
    errors = {}
    cn_no = (payload.get("cn_no") or "").strip()
    if not cn_no.isdigit():
        errors["cn_no"] = "C.N. no. must be a number."
    cn_date = _date(payload.get("cn_date"))
    if not cn_date:
        errors["cn_date"] = "Enter the C.N. date."
    code = (payload.get("party_code") or "").strip().upper()
    party = Party.objects.filter(party_code=code).first() if code else None
    if not party:
        errors["party_code"] = "Select a party."
    raw = payload.get("items") or []
    if not raw:
        errors["items"] = "Add at least one item."
    lines = []
    for n, r in enumerate(raw, start=1):
        item = Part.objects.filter(part_number=(r.get("item_code") or "").strip().upper()).first()
        if not item:
            errors["items"] = f"Row {n}: item isn't in the Item Master."
            break
        qty = _d(r.get("qty"))
        rate = _d(r.get("rate"))
        dis = _d(r.get("dis_pct")) or Decimal("0")
        if qty is None or qty <= 0:
            errors["items"] = f"Row {n}: quantity must be greater than zero."
            break
        if rate is None or rate < 0:
            errors["items"] = f"Row {n}: rate can't be negative."
            break
        lines.append({"item_code": item.part_number, "item_name": (item.description_1 or "")[:35],
                      "hsn_code": (item.hsn_code or "")[:8], "unit": (item.unit or "")[:3],
                      "qty": qty, "rate": rate, "dis_pct": dis})
    gst_pct = _d(payload.get("gst_pct")) or Decimal("0")
    freight = _d(payload.get("freight")) or Decimal("0")
    freight_gst_pct = _d(payload.get("freight_gst_pct")) or Decimal("0")
    adj_amt1 = _d(payload.get("adj_amt1")) or Decimal("0")
    adj_amt2 = _d(payload.get("adj_amt2")) or Decimal("0")
    if errors:
        raise CreditNoteError("Fix the highlighted fields.", errors)
    return cn_no, cn_date, party, lines, gst_pct, freight, freight_gst_pct, adj_amt1, adj_amt2


def _rate_bucket(gst_pct):
    """Which of the c_bill/g_master GST-rate buckets the note's single flat
    GST % belongs in. A rate that isn't one of the standard slabs is folded
    into the nearest bucket below it (never silently dropped from the
    taxable total); 0% goes in amt_tf, same as debit_note's taxable_0."""
    gst_int = int(gst_pct)
    if gst_int <= 0:
        return None
    for r in RATE_BUCKETS:
        if gst_int <= r:
            return r
    return RATE_BUCKETS[-1]


def _legacy_enabled():
    return "legacy" in settings.DATABASES and settings.LEGACY_WRITES_ENABLED


def save(payload, key=None, username=""):
    if not _legacy_enabled():
        raise CreditNoteError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    cn_no, cn_date, party, lines, gst_pct, freight, freight_gst_pct, adj_amt1, adj_amt2 = _validate(payload)
    t = totals(lines, gst_pct, freight, freight_gst_pct, adj_amt1, adj_amt2)
    intra_state = (party.supply_type or "").strip().upper() != "I"
    bucket = _rate_bucket(gst_pct)

    with transaction.atomic(using=GcBillHeader.objects.db):
        if key:
            if not GcBillHeader.objects.filter(_HEADER_TYPE, bill_no=key).exists():
                raise CreditNoteError("This credit note no longer exists.")
            if key != cn_no:
                raise CreditNoteError("C.N. no. can't be changed on an existing credit note.",
                                      {"cn_no": "C.N. no. is fixed."})
            old_lines = list(GMasterCreditLine.objects.filter(_LINE_TYPE, bill_no=cn_no).values("item_code", "qty"))
            for old in old_lines:
                _adjust_stock(old["item_code"], -(_d(old["qty"]) or Decimal("0")))
            GMasterCreditLine.objects.filter(_LINE_TYPE, bill_no=cn_no).delete()
        else:
            if GcBillHeader.objects.filter(_HEADER_TYPE, bill_no=cn_no).exists():
                raise CreditNoteError("C.N. no. already exists.", {"cn_no": "C.N. no. already exists."})
            counter = _first(InvNo.objects.select_for_update().values_list("next_cn_no", flat=True))
            if counter is None or int(counter) < int(cn_no):
                InvNo.objects.update(next_cn_no=int(cn_no))

        header = {
            "div": DIV, "b_date": cn_date, "ca_cr": "CR", "party_code": party.party_code, "bill_type": "C",
            "cstat": "W" if intra_state else "I",
            "gst_bill_no": (payload.get("gst_bill_no") or "")[:30], "gst_bill_date": _date(payload.get("gst_bill_date")),
            "gr_no": (payload.get("gr_no") or "")[:10], "gr_date": _date(payload.get("gr_date")),
            "transport": (payload.get("transport") or "")[:30], "remarks": (payload.get("remarks") or "")[:40],
            "amount": t["amount"], "gst_amt": t["gst_amt"] + t["freight_gst"], "n_amount": t["net"],
            "fr_rt": freight_gst_pct, "fr_amt": freight, "fr_amt1": t["freight_gst"],
            "adj1": "Y" if adj_amt1 else "", "adj_code1": (payload.get("adj_nar1") or "")[:4], "adj_amt1": adj_amt1,
            "adj2": "Y" if adj_amt2 else "", "adj_code2": (payload.get("adj_nar2") or "")[:4], "adj_amt2": adj_amt2,
            "amt_tf": Decimal("0"), "amt5": Decimal("0"), "amt12": Decimal("0"), "amt18": Decimal("0"), "amt28": Decimal("0"),
            "uname": (username or "")[:10],
        }
        for r in RATE_BUCKETS:
            header[f"cg_rt{r}"] = header[f"sg_amt{r}"] = header[f"cg_amt{r}"] = header[f"sg_rt{r}"] = Decimal("0")
            header[f"ig_rt{r}"] = header[f"ig_amt{r}"] = Decimal("0")
        if bucket is None:
            header["amt_tf"] = t["amount"]
        else:
            header[f"amt{bucket}"] = t["amount"]
            if intra_state:
                half = (t["gst_amt"] / 2).quantize(Q2, ROUND_HALF_UP)
                header[f"cg_rt{bucket}"] = header[f"sg_rt{bucket}"] = gst_pct / 2
                header[f"cg_amt{bucket}"] = half
                header[f"sg_amt{bucket}"] = t["gst_amt"] - half
            else:
                header[f"ig_rt{bucket}"] = gst_pct
                header[f"ig_amt{bucket}"] = t["gst_amt"]

        GcBillHeader.objects.update_or_create(bill_no=cn_no, defaults=header)

        GMasterCreditLine.objects.bulk_create([
            GMasterCreditLine(
                bill_no=cn_no, div=DIV, bill_type="C", line_date=cn_date, party_code=party.party_code,
                item_code=ln["item_code"], item_name=ln["item_name"], hsn_code=ln["hsn_code"], unit=ln["unit"],
                qty=ln["qty"], rate=ln["rate"], dis=ln["dis_pct"],
                dis_amt=(ln["qty"] * ln["rate"] * ln["dis_pct"] / Decimal("100")).quantize(Q2, ROUND_HALF_UP),
                amount=ln["amount"], gst=gst_pct, gst_amt=(ln["amount"] * gst_pct / Decimal("100")).quantize(Q2, ROUND_HALF_UP),
                sno=n, stts="B", cstat="W" if intra_state else "I", uname=(username or "")[:10],
            )
            for n, ln in enumerate(lines, start=1)
        ])

        for ln in lines:
            _adjust_stock(ln["item_code"], ln["qty"])
    return {"cn_no": cn_no, "net": f"{t['net']:.2f}"}


def new_save(payload, username=""):
    with transaction.atomic(using=GcBillHeader.objects.db):
        number = _allocate_cn_no()
        return save(dict(payload, cn_no=number), key=None, username=username)


def delete(cn_no):
    if not _legacy_enabled():
        raise CreditNoteError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    if not GcBillHeader.objects.filter(_HEADER_TYPE, bill_no=cn_no).exists():
        raise CreditNoteError("Credit note not found.")
    with transaction.atomic(using=GcBillHeader.objects.db):
        old_lines = list(GMasterCreditLine.objects.filter(_LINE_TYPE, bill_no=cn_no).values("item_code", "qty"))
        for old in old_lines:
            _adjust_stock(old["item_code"], -(_d(old["qty"]) or Decimal("0")))
        GMasterCreditLine.objects.filter(_LINE_TYPE, bill_no=cn_no).delete()
        GcBillHeader.objects.filter(_HEADER_TYPE, bill_no=cn_no).delete()
    return {"cn_no": cn_no}


def list_notes(start, end, search=""):
    qs = GcBillHeader.objects.filter(_HEADER_TYPE, b_date__gte=start, b_date__lte=end)
    headers = list(qs.values("bill_no", "b_date", "party_code", "n_amount"))
    codes = {h["party_code"] for h in headers if h["party_code"]}
    names = dict(Party.objects.filter(party_code__in=codes).values_list("party_code", "name"))
    cities = dict(Party.objects.filter(party_code__in=codes).values_list("party_code", "city"))
    term = (search or "").strip().lower()
    rows = []
    for h in headers:
        pname = _clean(names.get(h["party_code"])) or ""
        if term and term not in pname.lower():
            continue
        rows.append({
            "key": h["bill_no"], "cn_no": _clean(h["bill_no"]),
            "date": h["b_date"].isoformat() if h["b_date"] else "",
            "party_code": _clean(h["party_code"]), "party": pname, "city": (_clean(cities.get(h["party_code"])) or ""),
            "net": _money(h["n_amount"]),
        })
    rows.sort(key=lambda r: (r["date"], r["cn_no"]), reverse=True)
    return rows


def detail(cn_no):
    h = GcBillHeader.objects.filter(_HEADER_TYPE, bill_no=cn_no).first()
    if not h:
        return None
    lines = list(GMasterCreditLine.objects.filter(_LINE_TYPE, bill_no=cn_no).order_by("sno").values(
        "sno", "item_code", "item_name", "hsn_code", "unit", "qty", "rate", "dis", "amount"))
    party = Party.objects.filter(party_code=h.party_code).first()
    # Sliced, not .first() -- an unordered .first() makes Django add "ORDER BY
    # [id]", and this surrogate pk has no matching real column on g_master.
    gst_line = _first(GMasterCreditLine.objects.filter(_LINE_TYPE, bill_no=cn_no).values_list("gst", flat=True))
    return {
        "cn_no": _clean(h.bill_no), "cn_date": h.b_date.isoformat() if h.b_date else "",
        "gst_bill_no": _clean(h.gst_bill_no), "gst_bill_date": h.gst_bill_date.isoformat() if h.gst_bill_date else "",
        "gr_no": _clean(h.gr_no), "gr_date": h.gr_date.isoformat() if h.gr_date else "",
        "transport": _clean(h.transport), "remarks": _clean(h.remarks),
        "party_code": _clean(h.party_code), "party_name": _clean(party.name) if party else "",
        "city": _clean(party.city) if party else "",
        "gst_pct": f"{(gst_line or 0):.2f}",
        "freight": _money(h.fr_amt), "freight_gst_pct": _money(h.fr_rt),
        "adj_nar1": _clean(h.adj_code1), "adj_amt1": _money(h.adj_amt1),
        "adj_nar2": _clean(h.adj_code2), "adj_amt2": _money(h.adj_amt2),
        "net": _money(h.n_amount),
        "items": [
            {"sno": int(l["sno"] or 0), "item_code": _clean(l["item_code"]), "item_name": _clean(l["item_name"]),
             "hsn_code": _clean(l["hsn_code"]), "unit": _clean(l["unit"]), "qty": f"{(l['qty'] or 0):.3f}",
             "rate": f"{(l['rate'] or 0):.2f}", "dis_pct": f"{(l['dis'] or 0):.2f}", "amount": _money(l["amount"])}
            for l in lines
        ],
    }

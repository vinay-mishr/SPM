"""GST Credit Note (Narration) Entry: rate-wise (not item-wise), VFP "gcnar1" form."""
from datetime import date as _date_cls, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.parties.models import Party

from .narration_models import CBillHeader
from .models import InvNo

DIV = "SP"
Q2 = Decimal("0.01")
RATES = ("0", "5", "12", "18", "28")
TAX_RATES = ("5", "12", "18", "28")  # 0% carries no GST

_HEADER_TYPE = Q(bill_type=" ") | Q(bill_type="") | Q(bill_type__isnull=True)


class NarrationError(Exception):
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


def _highest_no():
    nums = [int(n) for n in CBillHeader.objects.filter(_HEADER_TYPE).values_list("bill_no", flat=True)
            if str(n).strip().isdigit()]
    return max(nums) if nums else 0


def next_cn_no():
    # Same physical counter (inv_no.gc_inv_no) the Spear Part credit note uses --
    # confirmed by the real VFP Add handler for this form reading/bumping it too.
    counter = _first(InvNo.objects.values_list("next_cn_no", flat=True))
    return str(max(int(counter) if counter is not None else 0, _highest_no()) + 1)


def _allocate_cn_no():
    counter = _first(InvNo.objects.select_for_update().values_list("next_cn_no", flat=True))
    new_no = max(int(counter) if counter is not None else 0, _highest_no()) + 1
    InvNo.objects.update(next_cn_no=new_no)
    return str(new_no)


def totals(taxable, dis_pct, cgst_in, sgst_in, igst_in, cess_amt):
    """
    Per-rate discount + taxable value, same shape as the VFP caltotal handler, minus
    its order-dependent variable reuse (which reads like a latent bug, not a rule
    worth preserving).

    CGST/SGST/IGST are no longer derived here from the party's within-state/
    interstate status -- they're user-editable on the entry screen (one amount per
    rate, submitted in cgst_in/sgst_in/igst_in), so whatever the user has on screen
    (auto-filled by the entry screen's own JS, or manually overridden) is what gets
    saved. 0% has no GST by definition, so it's always zero regardless of input.
    """
    buckets = {}
    amount = Decimal("0")
    gst_total = Decimal("0")
    for r in RATES:
        t = taxable.get(r, Decimal("0"))
        d = (t * dis_pct.get(r, Decimal("0")) / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
        taxable_val = (t - d).quantize(Q2, ROUND_HALF_UP)
        if r == "0":
            cgst = sgst = igst = Decimal("0")
        else:
            cgst = cgst_in.get(r, Decimal("0"))
            sgst = sgst_in.get(r, Decimal("0"))
            igst = igst_in.get(r, Decimal("0"))
        buckets[r] = {"camt": t, "dis_pct": dis_pct.get(r, Decimal("0")), "taxable": taxable_val,
                      "cgst": cgst, "sgst": sgst, "igst": igst}
        amount += taxable_val
        gst_total += cgst + sgst + igst
    net = (amount + gst_total + cess_amt).quantize(Q2, ROUND_HALF_UP)
    net_rounded = net.quantize(Decimal("1"), ROUND_HALF_UP)
    return buckets, amount, gst_total, net, net_rounded, (net_rounded - net)


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
    taxable, dis_pct = {}, {}
    for r in RATES:
        t = _d((payload.get("taxable") or {}).get(r))
        d = _d((payload.get("dis_pct") or {}).get(r)) or Decimal("0")
        if t is None or t < 0:
            errors[f"taxable_{r}"] = f"Sale {r}% taxable value is invalid."
        else:
            taxable[r] = t
            dis_pct[r] = d
    # CGST/SGST/IGST amounts: manually editable on the entry screen (one amount per
    # rate), so validated and saved as submitted rather than derived from the rate.
    cgst, sgst, igst = {}, {}, {}
    for r in TAX_RATES:
        for label, bucket, key in (("CGST", cgst, "cgst"), ("SGST", sgst, "sgst"), ("IGST", igst, "igst")):
            v = _d((payload.get(key) or {}).get(r))
            if v is None or v < 0:
                errors[f"{key}_{r}"] = f"Sale {r}% {label} amount is invalid."
            else:
                bucket[r] = v
    cess_amt = _d(payload.get("cess_amt")) or Decimal("0")
    if cess_amt < 0:
        errors["cess_amt"] = "Cess amount can't be negative."
    if errors:
        raise NarrationError("Fix the highlighted fields.", errors)
    return cn_no, cn_date, party, taxable, dis_pct, cgst, sgst, igst, cess_amt


def save(payload, key=None, username=""):
    if not ("legacy" in settings.DATABASES and settings.LEGACY_WRITES_ENABLED):
        raise NarrationError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    cn_no, cn_date, party, taxable, dis_pct, cgst, sgst, igst, cess_amt = _validate(payload)
    buckets, amount, gst_total, net, net_rounded, diff = totals(taxable, dis_pct, cgst, sgst, igst, cess_amt)

    with transaction.atomic(using=CBillHeader.objects.db):
        if key:
            if not CBillHeader.objects.filter(_HEADER_TYPE, bill_no=key).exists():
                raise NarrationError("This credit note no longer exists.")
            if key != cn_no:
                raise NarrationError("C.N. no. can't be changed on an existing credit note.",
                                     {"cn_no": "C.N. no. is fixed."})
        else:
            if CBillHeader.objects.filter(_HEADER_TYPE, bill_no=cn_no).exists():
                raise NarrationError("C.N. no. already exists.", {"cn_no": "C.N. no. already exists."})
            counter = _first(InvNo.objects.select_for_update().values_list("next_cn_no", flat=True))
            if counter is None or int(counter) < int(cn_no):
                InvNo.objects.update(next_cn_no=int(cn_no))

        header = {
            "div": DIV, "b_date": cn_date, "party_code": party.party_code, "bill_type": " ",
            "ag_bill": (payload.get("invoice_no") or "")[:20], "ag_date": _date(payload.get("invoice_date")),
            "p_sup": (payload.get("place_of_supply") or "")[:20], "pre1": (payload.get("pre_gst") or "")[:1],
            "nar1": (payload.get("nar1") or "")[:30], "nar2": (payload.get("nar2") or "")[:30],
            "nar3": (payload.get("nar3") or "")[:30], "nar4": (payload.get("nar4") or "")[:30],
            "amount": amount, "gst_amt": gst_total, "cess_amt1": cess_amt, "cess_rt": Decimal("0"),
            "diff_amt": diff, "n_amount": net_rounded,
            "uname": (username or "")[:10],
        }
        b0 = buckets["0"]
        header["camt0"], header["gdis0"], header["amt_tf"] = b0["camt"], b0["dis_pct"], b0["taxable"]
        for r in ("5", "12", "18", "28"):
            b = buckets[r]
            header[f"camt{r}"] = b["camt"]
            header[f"gdis{r}"] = b["dis_pct"]
            header[f"amt{r}"] = b["taxable"]
            header[f"cg_amt{r}"] = b["cgst"]
            header[f"sg_amt{r}"] = b["sgst"]
            header[f"ig_amt{r}"] = b["igst"]

        CBillHeader.objects.update_or_create(bill_no=cn_no, defaults=header)
    return {"cn_no": cn_no, "net": f"{net_rounded:.2f}"}


def new_save(payload, username=""):
    with transaction.atomic(using=CBillHeader.objects.db):
        number = _allocate_cn_no()
        return save(dict(payload, cn_no=number), key=None, username=username)


def delete(cn_no):
    if not ("legacy" in settings.DATABASES and settings.LEGACY_WRITES_ENABLED):
        raise NarrationError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    if not CBillHeader.objects.filter(_HEADER_TYPE, bill_no=cn_no).exists():
        raise NarrationError("Credit note not found.")
    with transaction.atomic(using=CBillHeader.objects.db):
        CBillHeader.objects.filter(_HEADER_TYPE, bill_no=cn_no).delete()
    return {"cn_no": cn_no}


def list_notes(start, end, search=""):
    qs = CBillHeader.objects.filter(_HEADER_TYPE, b_date__gte=start, b_date__lte=end)
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
    h = CBillHeader.objects.filter(_HEADER_TYPE, bill_no=cn_no).first()
    if not h:
        return None
    party = Party.objects.filter(party_code=h.party_code).first()
    taxable = {"0": h.camt0, "5": h.camt5, "12": h.camt12, "18": h.camt18, "28": h.camt28}
    dis_pct = {"0": h.gdis0, "5": h.gdis5, "12": h.gdis12, "18": h.gdis18, "28": h.gdis28}
    cgst = {"5": h.cg_amt5, "12": h.cg_amt12, "18": h.cg_amt18, "28": h.cg_amt28}
    sgst = {"5": h.sg_amt5, "12": h.sg_amt12, "18": h.sg_amt18, "28": h.sg_amt28}
    igst = {"5": h.ig_amt5, "12": h.ig_amt12, "18": h.ig_amt18, "28": h.ig_amt28}
    return {
        "cn_no": _clean(h.bill_no), "cn_date": h.b_date.isoformat() if h.b_date else "",
        "invoice_no": _clean(h.ag_bill), "invoice_date": h.ag_date.isoformat() if h.ag_date else "",
        "place_of_supply": _clean(h.p_sup), "pre_gst": _clean(h.pre1),
        "party_code": _clean(h.party_code), "party_name": _clean(party.name) if party else "",
        "city": _clean(party.city) if party else "",
        "supply_type": _clean(party.supply_type) if party else "",
        "nar1": _clean(h.nar1), "nar2": _clean(h.nar2), "nar3": _clean(h.nar3), "nar4": _clean(h.nar4),
        "taxable": {r: f"{(v or 0):.2f}" for r, v in taxable.items()},
        "dis_pct": {r: f"{(v or 0):.2f}" for r, v in dis_pct.items()},
        "cgst": {r: f"{(v or 0):.2f}" for r, v in cgst.items()},
        "sgst": {r: f"{(v or 0):.2f}" for r, v in sgst.items()},
        "igst": {r: f"{(v or 0):.2f}" for r, v in igst.items()},
        "cess_amt": _money(h.cess_amt1), "amount": _money(h.amount), "gst_amt": _money(h.gst_amt),
        "net": _money(h.n_amount),
    }

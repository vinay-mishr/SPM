"""Returnable challan reports and Challan Entry."""
from decimal import Decimal

from apps.mrn.services import _clean

# --- Party Wise Pending Challan ----------------------------------------------------------
#
# Old VFP report: "PARTY WISE PENDING CHALLAN". Challan lines of one party still pending
# (stts = 'B') dated in the range, grouped by party. Shows challan no, date, item, qty.

def pending_challan_report(party_code, start_date, end_date):
    from apps.parts.models import Part
    from apps.parties.models import Party
    from apps.returnable_challan.models import GchlLine

    lines = list(
        GchlLine.objects.filter(party_code=party_code.strip().upper(), status="B",
                                line_date__gte=start_date, line_date__lte=end_date)
        .values("chl_no", "line_date", "item_code", "item_name", "qty")
    )
    lines.sort(key=lambda r: (r["line_date"] or start_date, r["chl_no"] or ""))
    party = Party.objects.filter(party_code=party_code.strip().upper()).first()
    part_names = dict(Part.objects.filter(
        part_number__in={r["item_code"] for r in lines if r["item_code"]}
    ).values_list("part_number", "description_1"))
    result = []
    for r in lines:
        code = (r["item_code"] or "").strip()
        result.append({
            "chl_no": _clean(r["chl_no"]),
            "date": r["line_date"].isoformat() if r["line_date"] else "",
            "item_code": code,
            "item_name": _clean(r["item_name"] or part_names.get(code)),
            "qty": f"{(r['qty'] or 0):.3f}",
        })
    return {
        "party": {"code": party.party_code if party else "", "name": _clean(party.name) if party else "",
                  "city": _clean(party.city) if party else ""},
        "rows": result,
    }


# --- Challan Entry ------------------------------------------------------------------------
#
# Item-based, GST-aware (VFP "chl5" / "GCHL7" forms) -- see models.py's 2026-10-08
# note. Items are read/written on the shared ``imaster`` table
# (apps.purchase_orders.models.ItemMasterTransaction), not gchl_dat.

from datetime import date as _date  # noqa: E402
from decimal import ROUND_HALF_UP  # noqa: E402
from django.conf import settings as _settings  # noqa: E402
from django.db import transaction as _tx  # noqa: E402
from django.db.models import Q as _Q  # noqa: E402

from apps.parts.models import Part as _Part  # noqa: E402
from apps.parties.models import Party as _Party  # noqa: E402
from apps.gst.models import GstRate as _GstRate  # noqa: E402
from apps.purchase_orders.models import ItemMasterTransaction as _ItemTxn  # noqa: E402
from .models import GchlHeader as _Header, GchlLine as _Line, InvNo as _Inv  # noqa: E402

CHALLAN_PERMISSION = "returnable_challan.change_challan"
DIV = "SP"
_Q2 = Decimal("0.01")
_GST_RATES = (5, 12, 18, 28)

# Real gchl_mst rows (confirmed against the live legacy data) all have a blank
# "type" column -- none are 'I'. Reads tolerate both (new rows saved from this
# screen are still stamped 'I', so this never has to change again), otherwise
# every pre-existing challan was invisible to Challan Entry's own list/get/
# modify/delete.
_HEADER_TYPE = _Q(chl_type="I") | _Q(chl_type="") | _Q(chl_type__isnull=True)
_LINE_TYPE = _HEADER_TYPE
_ITEM_STATUS = "S"  # imaster rows that belong to a challan (matches the real rpldata)


class ChallanError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _money(v):
    return f"{(v or 0):.2f}"


def _first(qs):
    rows = list(qs[:1])
    return rows[0] if rows else None


def _clean_code(v):
    return (v or "").strip()[:4]


def _highest_no():
    nums = [int(n) for n in _Header.objects.filter(_HEADER_TYPE).values_list("chl_no", flat=True)
            if str(n).strip().isdigit()]
    return max(nums) if nums else 0


def next_challan_no():
    counter = _first(_Inv.objects.values_list("next_gchl_no", flat=True))
    return str(max(int(counter) if counter is not None else 0, _highest_no()) + 1)


def _allocate_challan_no():
    counter = _first(_Inv.objects.select_for_update().values_list("next_gchl_no", flat=True))
    new_no = max(int(counter) if counter is not None else 0, _highest_no()) + 1
    _Inv.objects.update(next_gchl_no=new_no)
    return str(new_no)


def list_challans(start, end, search=""):
    qs = _Header.objects.filter(_HEADER_TYPE, chl_date__gte=start, chl_date__lte=end)
    headers = list(qs.values("chl_no", "chl_date", "party_code", "amount", "n_amount", "phone", "adj"))
    names = dict(_Party.objects.filter(party_code__in={h["party_code"] for h in headers if h["party_code"]})
                 .values_list("party_code", "name"))
    cities = dict(_Party.objects.filter(party_code__in={h["party_code"] for h in headers if h["party_code"]})
                  .values_list("party_code", "city"))
    term = (search or "").strip().lower()
    rows = []
    for h in headers:
        pname = _clean(names.get(h["party_code"])) or "ACCOUNT NOT FOUND"
        if term and not pname.lower().startswith(term):
            continue
        rows.append({
            "key": h["chl_no"], "chl_no": _clean(h["chl_no"]),
            "date": h["chl_date"].isoformat() if h["chl_date"] else "",
            "party_code": _clean(h["party_code"]), "party_name": pname[:30],
            "city": (_clean(cities.get(h["party_code"])) or "")[:18],
            "amount": _money(h["n_amount"] if h["n_amount"] else h["amount"]), "phone": _clean(h["phone"]) or "",
            "adjusted": "Y" if (h["adj"] or "").strip().upper() == "Y" else "N",
        })
    rows.sort(key=lambda r: (r["date"], r["chl_no"]), reverse=True)
    return rows


# --- "ADD CHALLAN" import, for apps.spare_invoice's GST Billing (Spare Part) screen ------
#
# A challan's items become "billed" (bill_no set on their imaster row, see
# apps.spare_invoice.services.save_invoice) only when the invoice pulling them in is
# actually confirmed/saved -- importing into the on-screen grid and then exiting
# without saving leaves the challan fully available again. All-or-nothing per line
# (the real table has no column to track a partially-billed quantity): once a row's
# bill_no is set, the whole row is gone from this list, never split.

def list_pending_for_party(party_code):
    """[{chl_no, chl_date, item_count}] -- this party's challans that still have at
    least one not-yet-billed line, for the ADD CHALLAN picker dialog."""
    from collections import Counter

    party_code = (party_code or "").strip().upper()
    if not party_code:
        return []
    headers = list(_Header.objects.filter(_HEADER_TYPE, party_code=party_code).values("chl_no", "chl_date"))
    chl_nos = [h["chl_no"] for h in headers]
    unbilled = _ItemTxn.objects.filter(chl_no__in=chl_nos, status=_ITEM_STATUS).filter(
        _Q(bill_no__isnull=True) | _Q(bill_no="")
    ).values_list("chl_no", flat=True)
    counts = Counter(unbilled)
    rows = [
        {"chl_no": _clean(h["chl_no"]), "chl_date": h["chl_date"].isoformat() if h["chl_date"] else "",
         "item_count": counts[h["chl_no"]]}
        for h in headers if counts.get(h["chl_no"])
    ]
    rows.sort(key=lambda r: r["chl_no"])
    return rows


def get_pending_items(chl_no, party_code):
    """Not-yet-billed line items of one challan, for import into another invoice --
    or None if the challan doesn't exist / belongs to a different party than
    claimed (caller must not trust a bare chl_no without this check)."""
    party_code = (party_code or "").strip().upper()
    header = _Header.objects.filter(_HEADER_TYPE, chl_no=chl_no).first()
    if not header or (header.party_code or "").strip().upper() != party_code:
        return None
    # "order_no" and "particular" are real imaster columns distinct from the ORM
    # model's own mapped columns ("order" -> po_no, "remak" -> remarks) -- neither
    # is mapped by the model at all, so both have to be pulled in via RawSQL rather
    # than .values("order_no", "particular", ...).
    from django.db.models.expressions import RawSQL
    lines = list(_ItemTxn.objects.filter(chl_no=chl_no, status=_ITEM_STATUS).filter(
        _Q(bill_no__isnull=True) | _Q(bill_no="")
    ).annotate(
        order_no_raw=RawSQL("order_no", []), particular_raw=RawSQL("particular", []),
    ).order_by("sno").values(
        "sno", "item_code", "hsn_code", "quantity", "unit", "rate", "gst_percent", "order_no_raw", "particular_raw"))
    part_names = dict(_Part.objects.filter(
        part_number__in={l["item_code"] for l in lines if l["item_code"]}).values_list("part_number", "description_1"))
    return [
        {"sno": int(l["sno"] or 0), "item_code": _clean(l["item_code"]),
         "item_name": _clean(part_names.get((l["item_code"] or "").strip())),
         "hsn_code": _clean(l["hsn_code"]), "unit": _clean(l["unit"]),
         "qty": f"{(l['quantity'] or 0):.3f}", "rate": f"{(l['rate'] or 0):.4f}",
         # Use the GST% actually stored on the challan's own row at the time it was
         # made, not the Part Master's current rate (which may have changed since).
         "gst_pct": f"{(l['gst_percent'] or 0):.2f}",
         "order_no": _clean(l["order_no_raw"]) or "", "particular": _clean(l["particular_raw"]) or ""}
        for l in lines
    ]


def mark_consumed_if_fully_billed(chl_no):
    """Called after an invoice successfully pulls in some of this challan's lines
    -- mirrors the legacy rpldata's own "challan is marked adj='Y' once fully
    consumed" behaviour. No-op if the challan still has unbilled lines left."""
    still_pending = _ItemTxn.objects.filter(chl_no=chl_no, status=_ITEM_STATUS).filter(
        _Q(bill_no__isnull=True) | _Q(bill_no="")
    ).exists()
    if not still_pending:
        _Header.objects.filter(_HEADER_TYPE, chl_no=chl_no).update(adj="Y")


def get_challan(chl_no):
    h = _Header.objects.filter(_HEADER_TYPE, chl_no=chl_no).first()
    if not h:
        return None
    lines = list(_ItemTxn.objects.filter(chl_no=chl_no, status=_ITEM_STATUS).order_by("sno").values(
        "sno", "item_code", "hsn_code", "quantity", "unit", "rate", "amount", "gst_percent"))
    part_names = dict(_Part.objects.filter(
        part_number__in={l["item_code"] for l in lines if l["item_code"]}).values_list("part_number", "description_1"))
    party = _Party.objects.filter(party_code=h.party_code).first()
    net = h.n_amount if h.n_amount is not None else h.amount
    return {
        "chl_no": _clean(h.chl_no),
        "chl_date": h.chl_date.isoformat() if h.chl_date else "",
        "party_code": _clean(h.party_code),
        "party_name": _clean(party.name) if party else "ACCOUNT NOT FOUND",
        "city": _clean(party.city) if party else "",
        "phone": _clean(h.phone),
        "mode": _clean(h.mode),
        "ord_no": _clean(h.ord_no),
        "ord_date": h.ord_date.isoformat() if h.ord_date else "",
        "vehicle_no": _clean(h.vehicle_no),
        "supply_date": h.supply_date.isoformat() if h.supply_date else "",
        "supply_time": _clean(h.supply_time),
        "place_of_supply": _clean(h.place_of_supply),
        "particulars": _clean(h.remarks),
        "amount": _money(h.amount), "gst_amt": _money((net or Decimal("0")) - (h.amount or Decimal("0"))),
        "net_amount": _money(net),
        "adjusted": "Y" if (h.adj or "").strip().upper() == "Y" else "N",
        "items": [
            {"sno": int(l["sno"] or 0), "part_code": _clean(l["item_code"]),
             "part_name": _clean(part_names.get((l["item_code"] or "").strip())), "hsn_code": _clean(l["hsn_code"]),
             "qty": f"{(l['quantity'] or 0):.3f}", "unit": _clean(l["unit"]),
             "rate": f"{(l['rate'] or 0):.2f}", "amount": _money(l["amount"]),
             "gst_percent": f"{(l['gst_percent'] or 0):.2f}"}
            for l in lines
        ],
    }


def _validate(payload):
    errors = {}
    chl_no = (payload.get("chl_no") or "").strip()
    if not chl_no:
        errors["chl_no"] = "Challan no. is empty."
    elif not chl_no.isdigit():
        errors["chl_no"] = "Challan no. must be a number."
    if not payload.get("chl_date"):
        errors["chl_date"] = "Challan date is empty."
    party = (payload.get("party_code") or "").strip().upper()
    if not party:
        errors["party_code"] = "Select a party."
    elif not _Party.objects.filter(party_code=party).exists():
        errors["party_code"] = "Party not found in the Party Master."
    items = payload.get("items") or []
    if not items:
        errors["items"] = "Add at least one item."
    codes = {(i.get("part_code") or "").strip().upper() for i in items}
    parts = {p.part_number: p for p in _Part.objects.filter(part_number__in=codes)}
    cleaned = []
    for n, it in enumerate(items, start=1):
        code = (it.get("part_code") or "").strip().upper()
        part = parts.get(code)
        if not part:
            errors["items"] = f"Row {n}: item '{code}' isn't in the Item Master."
            break
        try:
            qty = Decimal(str(it.get("qty") or "0"))
            rate = Decimal(str(it.get("rate") or "0"))
        except Exception:
            errors["items"] = f"Row {n}: enter a valid quantity and rate."
            break
        if qty <= 0:
            errors["items"] = f"Row {n}: quantity must be more than 0."
            break
        if rate < 0:
            errors["items"] = f"Row {n}: rate can't be negative."
            break
        amount = (qty * rate).quantize(_Q2, ROUND_HALF_UP)
        gst_pct = Decimal(str(part.gst_percent or 0))
        if int(gst_pct) not in (0,) + _GST_RATES or gst_pct != int(gst_pct):
            errors["items"] = f"Row {n}: {code}'s GST % ({gst_pct}) must be one of 0, 5, 12, 18 or 28."
            break
        cleaned.append({"item_code": code, "item_name": (part.description_1 or "").strip()[:35],
                        "qty": qty, "rate": rate, "amount": amount, "gst_percent": gst_pct,
                        "hsn_code": (part.hsn_code or "").strip()[:8],
                        "unit": (part.unit or "").strip()[:3],
                        "particular": (it.get("particular") or "").strip()[:100]})
    if errors:
        raise ChallanError("Fix the highlighted fields.", errors)
    return chl_no, party, cleaned


def _rate_bucket(gst_pct):
    gst_int = int(gst_pct)
    if gst_int <= 0:
        return None
    for r in _GST_RATES:
        if gst_int <= r:
            return r
    return _GST_RATES[-1]


def totals(lines, intra_state):
    """Per-rate taxable value + GST, matching the real chl5 caltotal handler:
    each line's CGST/SGST amounts (within-state) always sum to its full tax,
    so the grand total needs no separate interstate branch."""
    buckets = {r: {"taxable": Decimal("0"), "gst": Decimal("0")} for r in _GST_RATES}
    taxable_tf = Decimal("0")
    amount = Decimal("0")
    gst_total = Decimal("0")
    for ln in lines:
        amount += ln["amount"]
        bucket = _rate_bucket(ln["gst_percent"])
        if bucket is None:
            taxable_tf += ln["amount"]
            continue
        gst_amt = (ln["amount"] * ln["gst_percent"] / Decimal("100")).quantize(_Q2, ROUND_HALF_UP)
        buckets[bucket]["taxable"] += ln["amount"]
        buckets[bucket]["gst"] += gst_amt
        gst_total += gst_amt
    net = (amount + gst_total).quantize(_Q2, ROUND_HALF_UP)
    return buckets, taxable_tf, amount, gst_total, net


def _gst_rates_by_rate():
    return {int(r.rate): r for r in _GstRate.objects.filter(rate__in=(0,) + _GST_RATES)}


def save_challan(payload, key=None, username=""):
    if "legacy" in _settings.DATABASES and not _settings.LEGACY_WRITES_ENABLED:
        raise ChallanError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    chl_no, party_code, cleaned = _validate(payload)
    party = _Party.objects.get(party_code=party_code)
    intra_state = (party.supply_type or "").strip().upper() != "I"
    buckets, taxable_tf, amount, gst_total, net = totals(cleaned, intra_state)
    freight = Decimal(str(payload.get("freight") or "0"))
    rates = _gst_rates_by_rate()

    header = {
        "chl_date": payload["chl_date"], "party_code": party_code, "ord_no": (payload.get("ord_no") or "")[:15],
        "ord_date": payload.get("ord_date") or None, "check_order": payload.get("check_order") or "N",
        "remarks": (payload.get("particulars") or "")[:100], "mode": (payload.get("mode") or "")[:20],
        "vehicle_no": (payload.get("vehicle_no") or "")[:20], "supply_date": payload.get("supply_date") or None,
        "supply_time": (payload.get("supply_time") or "")[:30], "place_of_supply": (payload.get("place_of_supply") or "")[:20],
        "phone": (payload.get("phone") or "")[:20], "amount": amount, "freight": freight, "n_amount": net,
        "amt_tf": taxable_tf, "sal_tf": _clean_code(getattr(rates.get(0), "sale_taxfree_account", None)),
    }
    for r in _GST_RATES:
        b = buckets[r]
        gr = rates.get(r)
        header[f"amt{r}"] = b["taxable"]
        if intra_state:
            half = (b["gst"] / 2).quantize(_Q2, ROUND_HALF_UP)
            header[f"cg_rt{r}"] = Decimal(r) / 2
            header[f"cg_amt{r}"] = half
            header[f"sg_rt{r}"] = Decimal(r) / 2
            header[f"sg_amt{r}"] = b["gst"] - half
            header[f"ig_rt{r}"] = header[f"ig_amt{r}"] = Decimal("0")
            header[f"sl_co{r}"] = _clean_code(getattr(gr, "sale_account", None))
            header[f"sc_cg{r}"] = _clean_code(getattr(gr, "sale_cgst_account", None))
            header[f"sc_sg{r}"] = _clean_code(getattr(gr, "sale_sgst_account", None))
            header[f"sc_ig{r}"] = ""
        else:
            header[f"cg_rt{r}"] = header[f"cg_amt{r}"] = header[f"sg_rt{r}"] = header[f"sg_amt{r}"] = Decimal("0")
            header[f"ig_rt{r}"] = Decimal(r)
            header[f"ig_amt{r}"] = b["gst"]
            header[f"sl_co{r}"] = _clean_code(getattr(gr, "sale_interstate_account", None))
            header[f"sc_cg{r}"] = header[f"sc_sg{r}"] = ""
            header[f"sc_ig{r}"] = _clean_code(getattr(gr, "sale_igst_account", None))

    with _tx.atomic(using=_Header.objects.db):
        if key:
            existing = _Header.objects.filter(_HEADER_TYPE, chl_no=key).first()
            if not existing:
                raise ChallanError("This challan no longer exists.")
            if (existing.adj or "").strip().upper() == "Y":
                raise ChallanError("Challan Adjusted Unable to Modify")
            if key != chl_no:
                raise ChallanError("Challan no. can't be changed on an existing challan.", {"chl_no": "Challan no. is fixed."})
            # Legacy deldata/rpldata only ever replaces rows where bill_no is still
            # empty (`scan for ... and empt(bill_no)`) -- a line already pulled onto
            # a real invoice (bill_no set) must survive a Modify untouched.
            _ItemTxn.objects.filter(chl_no=chl_no, status=_ITEM_STATUS).filter(
                _Q(bill_no__isnull=True) | _Q(bill_no="")
            ).delete()
            _Header.objects.filter(_HEADER_TYPE, chl_no=chl_no).update(**header)
        else:
            if _Header.objects.filter(_HEADER_TYPE, chl_no=chl_no).exists():
                raise ChallanError("CHALLAN NO ALREADY EXIST", {"chl_no": "This challan no. already exists."})
            counter = _first(_Inv.objects.select_for_update().values_list("next_gchl_no", flat=True))
            if counter is None or int(counter) < int(chl_no):
                _Inv.objects.update(next_gchl_no=int(chl_no))
            _Header.objects.create(chl_no=chl_no, div=DIV, chl_type="I", **header)
        _ItemTxn.objects.bulk_create([
            _ItemTxn(chl_no=chl_no, div=DIV, bill_date=payload["chl_date"], party_code=party_code,
                     item_code=i["item_code"], hsn_code=i["hsn_code"], quantity=i["qty"], unit=i["unit"],
                     rate=i["rate"], amount=i["amount"], gst_percent=i["gst_percent"],
                     gst_amount=(i["amount"] * i["gst_percent"] / Decimal("100")).quantize(_Q2, ROUND_HALF_UP),
                     sno=n, status=_ITEM_STATUS, uname=(username or "")[:10])
            for n, i in enumerate(cleaned, start=1)
        ])
    return {"chl_no": chl_no}


def get_challan_share_token(chl_no):
    """Returns a share token for this challan's public PDF link (minting one
    if needed), or None if the challan doesn't exist."""
    from .models import GchlShareLink

    if not _Header.objects.filter(_HEADER_TYPE, chl_no=chl_no).exists():
        return None
    return GchlShareLink.get_or_create_for(chl_no).token


def get_challan_by_share_token(token):
    """Returns the chl_no a still-valid share token points to, or None."""
    from .models import GchlShareLink

    link = GchlShareLink.objects.filter(token=token).first()
    if not link or not link.is_valid():
        return None
    return link.chl_no


def delete_challan(chl_no):
    with _tx.atomic(using=_Header.objects.db):
        header = _Header.objects.filter(_HEADER_TYPE, chl_no=chl_no).first()
        if not header:
            raise ChallanError("This challan no longer exists.")
        if (header.adj or "").strip().upper() == "Y":
            raise ChallanError("Challan Adjusted Unable to Delete")
        # Same legacy guard as the Modify path above -- `scan for ... and empt(bill_no)`
        # in the original deldata -- never delete a line already pulled onto a real
        # invoice (bill_no set).
        _ItemTxn.objects.filter(chl_no=chl_no, status=_ITEM_STATUS).filter(
            _Q(bill_no__isnull=True) | _Q(bill_no="")
        ).delete()
        _Header.objects.filter(_HEADER_TYPE, chl_no=chl_no).delete()
        counter = _first(_Inv.objects.select_for_update().values_list("next_gchl_no", flat=True))
        if counter is not None and chl_no.isdigit() and int(chl_no) == int(counter):
            _Inv.objects.update(next_gchl_no=int(counter) - 1)

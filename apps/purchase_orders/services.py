"""
Purchase Order Master logic (old software's pord_mst + order tables; old VFP form
``po1``, launched from ``PURCHASE ORDER FORM``). A PO has one header row (pord_mst)
and N line rows (order), one per part ordered. Because the ``order`` table has no
key of its own, CONFIRM always replaces every line row for one PO in a single
transaction (delete + re-insert), the same convention BOM Master uses for con-mst.
"""
from datetime import date as date_cls
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import models, transaction

from apps.bom.services import search_parts  # noqa: F401 -- re-exported for the views
from apps.creditor_outstanding.services import search_parties  # noqa: F401 -- re-exported
from apps.parties.models import Party
from apps.parties.services import company_state_code
from apps.parts.models import Part

from .models import (
    CreditorOut, ItemMasterTransaction, MrnData, PartRateHistory, PendingLetterShareLink, PurchaseOrderHeader,
    PurchaseOrderItem, PurchaseOrderShareLink,
)

PERMISSION = "purchase_orders.change_purchase_order"
DEFAULT_DIV = "SP"
MAX_QTY = Decimal("99999999.999")
MAX_RATE = Decimal("999999.9999")


class PurchaseOrderError(Exception):
    """A save / delete that must be refused, with a message for the user."""

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _db():
    return PurchaseOrderHeader.objects.db


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _money(value):
    return f"{(value or 0):.2f}"


def _qty(value):
    return f"{(value or 0):.3f}"


def _rate(value):
    return f"{(value or 0):.4f}"


def _party_names(codes):
    return dict(Party.objects.filter(party_code__in=set(codes)).values_list("party_code", "name"))


def _party_cities(codes):
    return dict(Party.objects.filter(party_code__in=set(codes)).values_list("party_code", "city"))


def _part_descriptions(codes):
    return dict(Part.objects.filter(part_number__in=set(codes)).values_list("part_number", "description_1"))


def next_po_number(div=DEFAULT_DIV):
    """Next PO no. for a division: highest existing number + 1 (the old software has
    no separate counter table for this; same "scan the existing max" convention used
    for Party/Vendor codes elsewhere in this project). This is only a preview for the
    Add form to show before anything is saved -- see _allocate_po_number() for the
    locked, authoritative allocation actually used at save time."""
    numbers = [
        int(n) for n in PurchaseOrderHeader.objects.filter(div=div).values_list("po_no", flat=True)
        if (n or "").strip().isdigit()
    ]
    return str((max(numbers) + 1) if numbers else 1)


def _allocate_po_number(div):
    """The real, locked allocation used inside save()'s own transaction. pord_mst has
    no counter row (unlike inv_no-backed numbering elsewhere in this project) and no
    real primary key/unique constraint on po_no to fall back on as a last-resort DB
    check, so two concurrent saves computing next_po_number() the plain way could both
    land on the same number. `select_for_update()` (SQL Server: UPDLOCK+HOLDLOCK,
    via django-mssql-backend) takes a range lock on this division's rows for the
    rest of the transaction, so a second concurrent caller blocks here until the
    first commits its new row, then sees it in its own MAX() scan."""
    numbers = [
        int(n) for n in
        PurchaseOrderHeader.objects.select_for_update().filter(div=div).values_list("po_no", flat=True)
        if (n or "").strip().isdigit()
    ]
    return str((max(numbers) + 1) if numbers else 1)


def list_orders(div=None):
    """All PO headers (optionally one division), newest first."""
    qs = PurchaseOrderHeader.objects.all()
    if div:
        qs = qs.filter(div=div)
    rows = list(qs.order_by("-order_date", "-po_no").values("div", "po_no", "order_date", "party_code", "amount", "net_amount", "uname"))
    names = _party_names(r["party_code"] for r in rows)
    cities = _party_cities(r["party_code"] for r in rows)
    result = []
    for sno, r in enumerate(rows, start=1):
        party = (r["party_code"] or "").strip()
        result.append({
            "sno": sno,
            "key": f"{(r['div'] or '').strip()}|{r['po_no']}",
            "div": (r["div"] or "").strip(),
            "po_no": r["po_no"],
            "order_date": r["order_date"].isoformat() if r["order_date"] else "",
            "party_code": party,
            "party_name": _clean(names.get(party)),
            "city": _clean(cities.get(party)),
            "amount": _money(r["amount"]),
            "net_amount": _money(r["net_amount"]),
            "uname": _clean(r["uname"]),
        })
    return result


def get_po_share_token(div, po_no):
    """Token for a public, no-login link to this PO's print view (for sharing
    e.g. over WhatsApp) -- reuses one already issued for this PO if it's still
    valid, rather than minting (and invalidating) a new one on every share."""
    if not PurchaseOrderHeader.objects.filter(div=div, po_no=po_no).exists():
        return None
    return PurchaseOrderShareLink.get_or_create_for(div, po_no).token


def get_order_by_share_token(token):
    """The PO a public share link's token points to, or None if the token is
    unknown, expired, or has been revoked."""
    link = PurchaseOrderShareLink.objects.filter(token=token).first()
    if not link or not link.is_valid():
        return None
    return get_order(link.div, link.po_no)


def get_order(div, po_no):
    """One PO's header + its line rows, with part descriptions filled in."""
    header = PurchaseOrderHeader.objects.filter(div=div, po_no=po_no).first()
    if not header:
        return None
    lines = list(
        PurchaseOrderItem.objects.filter(div=div, po_no=po_no)
        .order_by("part_code")
        .values(
            "part_code", "despatch_date", "po_qty", "quantity", "unit", "hsn_code", "rate", "size",
            "discount_percent", "particulars", "gst_rate",
        )
    )
    codes = [r["part_code"] for r in lines]
    names = _part_descriptions(codes)
    materials = dict(Part.objects.filter(part_number__in=set(codes)).values_list("part_number", "material"))
    total_discount = sum(
        (r["quantity"] or 0) * (r["rate"] or 0) * (r["discount_percent"] or 0) / 100 for r in lines
    )
    party_mobile = ""
    if header.party_code:
        party = Party.objects.filter(party_code=header.party_code).first()
        party_mobile = (party.mobile_1 or "").strip() if party else ""
    return {
        "div": (header.div or "").strip(),
        "po_no": header.po_no,
        "order_date": header.order_date.isoformat() if header.order_date else "",
        "party_code": (header.party_code or "").strip(),
        "party_mobile": party_mobile,
        "amount": _money(header.amount),
        # Gross, before the per-line discount -- "amount"/header.amount above is
        # already net of it, so printing this on the Purchase Order and
        # subtracting "discount_amount" from it is what shows the discount
        # actually being taken off, instead of looking like it was never
        # applied. The Net Amount this adds up to is unchanged either way.
        "gross_amount": _money((header.amount or 0) + total_discount),
        "gst_amount": _money(header.gst_amount),
        "net_amount": _money(header.net_amount),
        "discount_amount": _money(total_discount),
        "remarks": _clean(header.remarks),
        "payment": _clean(header.payment),
        "note": _clean(header.note),
        "lines": [
            {
                "part_code": _clean(r["part_code"]),
                "part_name": _clean(names.get(r["part_code"])),
                "material": _clean(materials.get(r["part_code"])),
                "despatch_date": r["despatch_date"].isoformat() if r["despatch_date"] else "",
                "po_qty": _qty(r["po_qty"]),
                "quantity": _qty(r["quantity"]),
                "unit": _clean(r["unit"]),
                "hsn_code": _clean(r["hsn_code"]),
                "rate": _rate(r["rate"]),
                "size": _clean(r["size"]),
                "discount_percent": f"{(r['discount_percent'] or 0):.2f}",
                "particulars": _clean(r["particulars"]),
                "gst_percent": f"{(r['gst_rate'] or 0):.2f}",
                # Amount is already net of the line discount (see _line_amount); the
                # discount amount itself is shown only as extra information on the
                # printed PO, not added into the totals again (it's already baked
                # into Amount / header.amount).
                "discount_amount": _money(
                    (r["quantity"] or 0) * (r["rate"] or 0) * (r["discount_percent"] or 0) / 100
                ),
                "amount": _money(_line_amount(r["quantity"], r["rate"], r["discount_percent"])),
            }
            for r in lines
        ],
    }


def _line_amount(quantity, rate, discount_percent):
    """Qty * Rate, less Discount % -- the taxable value GST is computed on."""
    base = (quantity or Decimal("0")) * (rate or Decimal("0"))
    return base * (Decimal("1") - (discount_percent or Decimal("0")) / Decimal("100"))


def part_reference(part_code, vendor_code=""):
    """Reference fields shown when a part is picked on the PO line (old VFP:
    unit/gst/hsn/rate/packing/current stock/material, and -- if the chosen vendor is
    one of the part's own 4 registered suppliers -- that supplier's own rate1-4)."""
    part = Part.objects.filter(part_number=part_code).first()
    if not part:
        return None
    rate = part.purchase_rate
    vendor_code = (vendor_code or "").strip().upper()
    for n in "1234":
        if vendor_code and _clean(getattr(part, f"supplier_{n}")).upper() == vendor_code:
            rate = getattr(part, f"rate_{n}") or rate
            break
    return {
        "part_code": _clean(part.part_number),
        "description": _clean(part.description_1),
        "material": _clean(part.material),
        "unit": _clean(part.unit),
        "gst_percent": _rate(part.gst_percent)[:-2],  # 2 decimals is enough for a % rate
        "hsn_code": _clean(part.hsn_code),
        "rate": _rate(rate),
        "packing": int(part.packing) if part.packing is not None else 0,
        "current_stock": _qty(part.current_stock),
        "size": _clean(part.gauge),
    }


def last_rate(part_code):
    """Most recent rt_mst rate for this part (old VFP: rt_mst filtered on i_code, go
    bottom). No reliable row-order column exists, so "most recent" = latest date."""
    row = PartRateHistory.objects.filter(part_code=part_code).order_by("-order_date").first()
    return _rate(row.rate) if row else _rate(0)


def previous_info(part_code, limit=25):
    """Purchase history for one part (old VFP: DO FORM previnfo2 WITH i_code)."""
    rows = PartRateHistory.objects.filter(part_code=part_code).order_by("-order_date")[:limit]
    codes = [r.party_code for r in rows]
    names = _party_names(codes)
    return [
        {
            "date": r.order_date.isoformat() if r.order_date else "",
            "party_code": _clean(r.party_code),
            "party_name": _clean(names.get(r.party_code)),
            "quantity": _qty(r.quantity),
            "rate": _rate(r.rate),
        }
        for r in rows
    ]


def gst_split(gst_percent, party_code):
    """CGST+SGST (within the company's own state) or IGST (interstate), matching the
    Vendor/Party "W / I" convention already used throughout this project."""
    gst_percent = gst_percent or Decimal("0")
    party = Party.objects.filter(party_code=party_code).first()
    party_state = (party.state_gst_code if party else "") or ""
    within = not party_state or party_state == company_state_code()
    if within:
        half = (gst_percent / 2).quantize(Decimal("0.01"))
        return {"cgst_rate": half, "sgst_rate": half, "igst_rate": Decimal("0")}
    return {"cgst_rate": Decimal("0"), "sgst_rate": Decimal("0"), "igst_rate": gst_percent}


def _parse_decimal(raw, field_label, max_value, required=True):
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if text == "":
        if required:
            raise ValueError(f"Enter the {field_label}.")
        return Decimal("0")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Enter a number for {field_label}.")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field_label} cannot be negative.")
    if value > max_value:
        raise ValueError(f"{field_label} is too large.")
    return value


def _require_writes():
    if not writes_enabled():
        raise PurchaseOrderError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _validate_lines(rows):
    if not isinstance(rows, list) or not rows:
        raise PurchaseOrderError("Add at least one item.", {"": "Add at least one item."})
    known_parts = set(Part.objects.filter(
        part_number__in={(row or {}).get("part_code", "").strip().upper() for row in rows}
    ).values_list("part_number", flat=True))

    errors = {}
    cleaned = []
    for index, row in enumerate(rows):
        row = row or {}
        key = f"row{index}"
        part_code = str(row.get("part_code", "")).strip().upper()
        if not part_code:
            errors[key] = "Select a part."
            continue
        if part_code not in known_parts:
            errors[key] = f"Part {part_code} was not found in Part Master."
            continue
        try:
            po_qty = _parse_decimal(row.get("po_qty"), "P.O. quantity", MAX_QTY)
            quantity = _parse_decimal(row.get("quantity", row.get("po_qty")), "quantity", MAX_QTY)
            rate = _parse_decimal(row.get("rate"), "rate", MAX_RATE)
            discount_percent = _parse_decimal(row.get("discount_percent"), "discount %", Decimal("100"), required=False)
        except ValueError as exc:
            errors[key] = str(exc)
            continue
        if po_qty <= 0:
            errors[key] = "P.O. quantity must be more than 0."
            continue
        cleaned.append({
            "part_code": part_code,
            "po_qty": po_qty,
            "quantity": quantity,
            "unit": _clean(row.get("unit"))[:3],
            "hsn_code": _clean(row.get("hsn_code"))[:8],
            "rate": rate,
            "discount_percent": discount_percent,
            "size": _clean(row.get("size"))[:12],
            "particulars": _clean(row.get("particulars")),
            "despatch_date": row.get("despatch_date") or None,
            "gst_percent": _parse_decimal(row.get("gst_percent"), "GST %", Decimal("100"), required=False),
        })
    if errors:
        raise PurchaseOrderError("Some item rows are not valid.", errors)
    return cleaned


def save(div, po_no, party_code, order_date, lines, username="", key=None, remarks="", payment="", note=""):
    """CONFIRM: create (key is None) or replace (key given) one PO header + all its
    line rows in a single transaction, matching BOM Master's replace-all convention."""
    _require_writes()
    div = (div or DEFAULT_DIV).strip().upper() or DEFAULT_DIV
    party_code = (party_code or "").strip().upper()
    remarks = (remarks or "").strip()
    payment = (payment or "").strip()
    note = (note or "").strip()
    errors = {}
    if not party_code:
        errors["party_code"] = "Select a party."
    elif not Party.objects.filter(party_code=party_code).exists():
        errors["party_code"] = "Select a party from the Party Master."
    if not order_date:
        errors["order_date"] = "PO date is required."
    if errors:
        raise PurchaseOrderError("Fix the highlighted fields.", errors)

    cleaned = _validate_lines(lines)

    total_amount = Decimal("0")
    total_gst = Decimal("0")
    line_objects = []
    for row in cleaned:
        amount = _line_amount(row["quantity"], row["rate"], row["discount_percent"]).quantize(Decimal("0.01"))
        gst = gst_split(row["gst_percent"], party_code)
        gst_amount = (amount * (row["gst_percent"] or Decimal("0")) / Decimal("100")).quantize(Decimal("0.01"))
        total_amount += amount
        total_gst += gst_amount
        line_objects.append(PurchaseOrderItem(
            div=div, part_code=row["part_code"], order_date=order_date, party_code=party_code,
            po_qty=row["po_qty"], unit=row["unit"], rate=row["rate"], discount_percent=row["discount_percent"],
            despatch_date=row["despatch_date"],
            quantity=row["quantity"], hsn_code=row["hsn_code"], size=row["size"], particulars=row["particulars"],
            cgst_rate=gst["cgst_rate"], sgst_rate=gst["sgst_rate"], igst_rate=gst["igst_rate"],
            cgst_amount=(amount * gst["cgst_rate"] / Decimal("100")).quantize(Decimal("0.01")),
            sgst_amount=(amount * gst["sgst_rate"] / Decimal("100")).quantize(Decimal("0.01")),
            igst_amount=(amount * gst["igst_rate"] / Decimal("100")).quantize(Decimal("0.01")),
            gst_rate=row["gst_percent"], gst_amount=gst_amount, uname=username[:10],
        ))

    with transaction.atomic(using=_db()):
        if key:
            old_div, old_po_no = key
            PurchaseOrderItem.objects.filter(div=old_div, po_no=old_po_no).delete()
            po_no = old_po_no
        else:
            po_no = _allocate_po_number(div)
            PurchaseOrderHeader.objects.create(
                div=div, po_no=po_no, order_date=order_date, party_code=party_code,
                amount=total_amount, gst_amount=total_gst, net_amount=total_amount + total_gst,
                remarks=remarks[:30], payment=payment[:30], note=note,
                uname=username[:10],
            )
        if key:
            PurchaseOrderHeader.objects.filter(div=old_div, po_no=old_po_no).update(
                order_date=order_date, party_code=party_code,
                amount=total_amount, gst_amount=total_gst, net_amount=total_amount + total_gst,
                remarks=remarks[:30], payment=payment[:30], note=note,
            )
        for line in line_objects:
            line.po_no = po_no
        PurchaseOrderItem.objects.bulk_create(line_objects)

    return div, po_no


def delete_order(div, po_no):
    _require_writes()
    with transaction.atomic(using=_db()):
        deleted, _ = PurchaseOrderHeader.objects.filter(div=div, po_no=po_no).delete()
        if not deleted:
            raise PurchaseOrderError("This purchase order was not found.")
        PurchaseOrderItem.objects.filter(div=div, po_no=po_no).delete()


# --- Party Wise Pending Purchase Order report ------------------------------------------------
#
# Old VFP form: "PARTY-WISE PENDING P.O.". A PO line is pending when:
#   date <= as_on_date  AND  stk_qty - rec_qty > 0  AND  adj == '' (still open)
# Selective narrows to one party (p_code == the chosen party's code); All covers every party.

def pending_orders(as_on_date, party_code=None):
    """[{party: {...}, lines: [...]}] -- pending PO lines, party-wise, sorted by party name."""
    # adj == '' (blank) means still open/pending in the old software; live data currently has
    # no other value, but any non-blank adj code is excluded to match the VFP filter exactly.
    qs = PurchaseOrderItem.objects.filter(order_date__lte=as_on_date).filter(
        models.Q(adjusted__isnull=True) | models.Q(adjusted__in=["", " "])
    )
    if party_code:
        qs = qs.filter(party_code=party_code.strip().upper())
    lines = list(qs.values(
        "div", "po_no", "part_code", "order_date", "party_code", "quantity", "received_qty", "rate", "despatch_date",
    ))
    # stk_qty - rec_qty > 0 (received_qty can be NULL -- treated as 0, matching the VFP default).
    # NOTE: VFP's "stk_qty" is this model's `quantity` field (db_column stk_qty), not `po_qty`
    # (db_column stock) -- confirmed against the Item Wise Pending P.O. report's explicit
    # ORD.QTY = stk_qty mapping.
    lines = [r for r in lines if (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0")) > 0]

    party_codes = {r["party_code"] for r in lines if r["party_code"]}
    parties = {
        p.party_code: p for p in Party.objects.filter(party_code__in=party_codes)
    }
    part_names = {
        code: name for code, name in Part.objects.filter(
            part_number__in={r["part_code"] for r in lines if r["part_code"]}
        ).values_list("part_number", "description_1")
    }

    grouped = {}
    for r in lines:
        code = (r["party_code"] or "").strip()
        party = parties.get(code)
        pending_qty = (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0"))
        value = (pending_qty * (r["rate"] or Decimal("0"))).quantize(Decimal("0.01"))
        delay_days = (as_on_date - r["despatch_date"]).days if r["despatch_date"] else None
        entry = grouped.setdefault(code, {
            "party_code": code,
            "party_name": (party.name if party else "").strip() if party else "",
            "city": (party.city if party else "") or "",
            "grade": (party.grade if party else "") or "",
            "lines": [],
        })
        entry["lines"].append({
            "ord_no": f"{(r['div'] or '').strip()}/{r['po_no']}",
            "ord_date": r["order_date"].isoformat() if r["order_date"] else "",
            "item_code": (r["part_code"] or "").strip(),
            "item_name": (part_names.get(r["part_code"]) or "").strip(),
            "pending_qty": f"{pending_qty:.3f}",
            "rate": f"{(r['rate'] or 0):.2f}",
            "value": f"{value:.2f}",
            "despatch_date": r["despatch_date"].isoformat() if r["despatch_date"] else "",
            "delay_days": delay_days,
        })

    return sorted(grouped.values(), key=lambda g: g["party_name"] or g["party_code"])


# --- Party-Wise Purchase Order Adjustment report -----------------------------------------------
#
# Old VFP form: "PARTY-WISE PURCHASE ORDER ADJUSTMENT". Its Excel button scans the same
# PO lines as the Party Wise Pending P.O. report above, but the other way round -- only
# lines that HAVE been adjusted:
#   date <= run_date  AND  stk_qty - rec_qty > 0  AND  adj == 'Y'
# All = every party; Single narrows to one party (p_code == the chosen party's code).

def party_wise_po_adjustment(run_date, party_code=None):
    """[{party_code, party_name, city, lines: [...]}] -- adjusted PO lines, party-wise,
    sorted by party name, for the Excel export only (this report has no on-screen grid
    in the old software, same as Party Wise Pending P.O. Despatch Report)."""
    qs = PurchaseOrderItem.objects.filter(order_date__lte=run_date, adjusted="Y")
    if party_code:
        qs = qs.filter(party_code=party_code.strip().upper())
    lines = list(qs.values("div", "po_no", "part_code", "order_date", "party_code", "quantity", "received_qty"))
    lines = [r for r in lines if (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0")) > 0]
    lines.sort(key=lambda r: r["order_date"] or date_cls.min)

    party_codes = {r["party_code"] for r in lines if r["party_code"]}
    parties = {p.party_code: p for p in Party.objects.filter(party_code__in=party_codes)}
    part_names = dict(Part.objects.filter(
        part_number__in={r["part_code"] for r in lines if r["part_code"]}
    ).values_list("part_number", "description_1"))

    grouped = {}
    for r in lines:
        code = (r["party_code"] or "").strip()
        party = parties.get(code)
        pending_qty = (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0"))
        entry = grouped.setdefault(code, {
            "party_code": code,
            "party_name": (party.name if party else "").strip() if party else "",
            "city": (party.city if party else "") or "",
            "lines": [],
        })
        entry["lines"].append({
            "ord_no": f"{(r['div'] or '').strip()}/{r['po_no']}",
            "ord_date": r["order_date"].isoformat() if r["order_date"] else "",
            "item_code": (r["part_code"] or "").strip(),
            "item_name": (part_names.get(r["part_code"]) or "").strip(),
            "pending_qty": f"{pending_qty:.3f}",
        })

    return sorted(grouped.values(), key=lambda g: g["party_name"] or g["party_code"])


# --- Party Wise Pending P.O. Despatch report --------------------------------------------------
#
# Old VFP form: "PARTY-WISE PENDING P.O. DESPATCH REPORT". A PO line is pending when:
#   dd_date >= start_date  AND  dd_date <= end_date  AND  stk_qty - rec_qty > 0
# (unlike the plain Pending P.O. report above, this one does NOT check adj, and it filters
# on the despatch date range rather than the order date). Delay Days is run_date - dd_date,
# where run_date is a separate value from the start/end filter range.

def pending_despatch(start_date, end_date, run_date, party_code=None, item_code=None):
    """[{party_code, party_name, city, lines: [...]}] -- pending despatches, party-wise,
    ordered by party name then despatch date (old VFP: SET ORDER TO cname / dd_date)."""
    qs = PurchaseOrderItem.objects.filter(despatch_date__gte=start_date, despatch_date__lte=end_date)
    if party_code:
        qs = qs.filter(party_code=party_code.strip().upper())
    if item_code:
        qs = qs.filter(part_code=item_code.strip().upper())
    lines = list(qs.values(
        "div", "po_no", "part_code", "order_date", "party_code", "quantity", "received_qty", "despatch_date",
    ))
    # VFP's "stk_qty" is this model's `quantity` field (db_column stk_qty), not `po_qty`.
    lines = [r for r in lines if (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0")) > 0]
    lines.sort(key=lambda r: r["despatch_date"] or date_cls.min)

    party_codes = {r["party_code"] for r in lines if r["party_code"]}
    parties = {p.party_code: p for p in Party.objects.filter(party_code__in=party_codes)}
    part_names = {
        code: name for code, name in Part.objects.filter(
            part_number__in={r["part_code"] for r in lines if r["part_code"]}
        ).values_list("part_number", "description_1")
    }

    grouped = {}
    for r in lines:
        code = (r["party_code"] or "").strip()
        party = parties.get(code)
        pending_qty = (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0"))
        delay_days = (run_date - r["despatch_date"]).days if r["despatch_date"] else None
        entry = grouped.setdefault(code, {
            "party_code": code,
            "party_name": (party.name if party else "").strip() if party else "",
            "city": (party.city if party else "") or "",
            "lines": [],
        })
        entry["lines"].append({
            "ord_no": f"{(r['div'] or '').strip()}/{r['po_no']}",
            "ord_date": r["order_date"].isoformat() if r["order_date"] else "",
            "item_code": (r["part_code"] or "").strip(),
            "item_name": (part_names.get(r["part_code"]) or "").strip(),
            "pending_qty": f"{pending_qty:.3f}",
            "despatch_date": r["despatch_date"].isoformat() if r["despatch_date"] else "",
            "delay_days": delay_days,
        })

    return sorted(grouped.values(), key=lambda g: g["party_name"] or g["party_code"])


# --- Item Wise Pending Purchase Order report --------------------------------------------------
#
# Old VFP form: "ITEM-WISE PENDING P.O." (part-mst is aliased/labelled "item" on this screen).
# A PO line is pending when:  date <= run_date  AND  stk_qty - rec_qty > 0
# (no adj check here, matching the VFP scan condition literally). All = every part; Single
# narrows to one part (icod == the chosen part's code). Grouped/ordered by item name (i_name).

def item_wise_pending(run_date, part_code=None):
    """[{part_code, part_name, lines: [...]}] -- pending PO lines, item-wise, ordered by item name."""
    qs = PurchaseOrderItem.objects.filter(order_date__lte=run_date)
    if part_code:
        qs = qs.filter(part_code=part_code.strip().upper())
    lines = list(qs.values(
        "div", "po_no", "part_code", "order_date", "party_code", "quantity", "received_qty", "despatch_date",
    ))
    lines = [r for r in lines if (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0")) > 0]

    parts = {
        p.part_number: p for p in Part.objects.filter(
            part_number__in={r["part_code"] for r in lines if r["part_code"]}
        )
    }
    party_names = dict(Party.objects.filter(
        party_code__in={r["party_code"] for r in lines if r["party_code"]}
    ).values_list("party_code", "name"))
    party_cities = dict(Party.objects.filter(
        party_code__in={r["party_code"] for r in lines if r["party_code"]}
    ).values_list("party_code", "city"))

    grouped = {}
    for r in lines:
        code = (r["part_code"] or "").strip()
        part = parts.get(code)
        ord_qty = r["quantity"] or Decimal("0")
        rec_qty = r["received_qty"] or Decimal("0")
        entry = grouped.setdefault(code, {
            "part_code": code,
            "part_name": (part.description_1 if part else "").strip() if part else "",
            "lines": [],
        })
        entry["lines"].append({
            "ord_no": f"{(r['div'] or '').strip()}/{r['po_no']}",
            "ord_date": r["order_date"].isoformat() if r["order_date"] else "",
            "party_code": (r["party_code"] or "").strip(),
            "party_name": (party_names.get(r["party_code"]) or "").strip(),
            "city": (party_cities.get(r["party_code"]) or "").strip(),
            "ord_qty": f"{ord_qty:.3f}",
            "rec_qty": f"{rec_qty:.3f}",
            "bal_qty": f"{ord_qty - rec_qty:.3f}",
            "despatch_date": r["despatch_date"].isoformat() if r["despatch_date"] else "",
        })

    return sorted(grouped.values(), key=lambda g: g["part_name"] or g["part_code"])


# --- Monthly Order Report -----------------------------------------------------------------
#
# New report (no corresponding old VFP form/report under this exact name): one flat row
# per PO line placed within a date range, unlike the grouped, pending-only reports above --
# every order line in range is shown, including fully received ones (BAL.QTY 0.00) and
# over-received ones (a negative BAL.QTY, never clamped to zero). Condition:
#   start_date <= order_date <= end_date
# Field mapping (confirmed against Item Wise Pending P.O., which maps the same fields):
# ORD.QTY = PurchaseOrderItem.quantity (stk_qty), REC.QTY = received_qty (rec_qty),
# DES.DATE = despatch_date (dd_date). Sorted by order date then order no, matching the
# reference screenshot's row order.

def monthly_order_report(start_date, end_date):
    """[{item_name, ord_no, ord_date, party_name, city, ord_qty, rec_qty, bal_qty,
    despatch_date}, ...] -- every PO line ordered within the date range, flat (not
    grouped), sorted by order date then order no."""
    rows = list(
        PurchaseOrderItem.objects.filter(order_date__gte=start_date, order_date__lte=end_date)
        .values("div", "po_no", "part_code", "order_date", "party_code", "quantity", "received_qty", "despatch_date")
    )
    rows.sort(key=lambda r: (r["order_date"] or date_cls.min, r["po_no"] or ""))

    part_names = dict(Part.objects.filter(
        part_number__in={r["part_code"] for r in rows if r["part_code"]}
    ).values_list("part_number", "description_1"))
    party_names = dict(Party.objects.filter(
        party_code__in={r["party_code"] for r in rows if r["party_code"]}
    ).values_list("party_code", "name"))
    party_cities = dict(Party.objects.filter(
        party_code__in={r["party_code"] for r in rows if r["party_code"]}
    ).values_list("party_code", "city"))

    result = []
    for r in rows:
        ord_qty = r["quantity"] or Decimal("0")
        rec_qty = r["received_qty"] or Decimal("0")
        party_code = (r["party_code"] or "").strip()
        result.append({
            "item_name": (part_names.get((r["part_code"] or "").strip()) or "").strip(),
            "ord_no": f"{(r['div'] or '').strip()}{r['po_no'] or ''}",
            "ord_date": r["order_date"].isoformat() if r["order_date"] else "",
            "party_name": (party_names.get(party_code) or "").strip(),
            "city": (party_cities.get(party_code) or "").strip(),
            "ord_qty": f"{ord_qty:.2f}",
            "rec_qty": f"{rec_qty:.2f}",
            "bal_qty": f"{ord_qty - rec_qty:.2f}",
            "despatch_date": r["despatch_date"].isoformat() if r["despatch_date"] else "",
        })
    return result


# --- Monthly Purchase Report ---------------------------------------------------------------
#
# Old VFP form/report: "PURCHASE REPORT". Read-only: every row where
#   mrn_dt >= start_date  AND  mrn_dt <= end_date  AND  job_type == '' (blank)
# Gross Amt is cr_out.amt when it is set and non-zero, otherwise the matching
# mrn_dat.amount (looked up by mrn_no) -- exactly the old report's fallback rule.

def monthly_purchase_report(start_date, end_date):
    """[{code, party_name, bill_no, bill_date, mrn_no, mrn_date, gross_amount, net_amount}, ...]
    ordered by MRN date then MRN no. (old VFP: SET FILTER ... GO TOP ... SCAN, table order)."""
    rows = list(
        CreditorOut.objects.filter(mrn_date__gte=start_date, mrn_date__lte=end_date)
        .filter(models.Q(job_type__isnull=True) | models.Q(job_type=""))
        .order_by("mrn_date", "mrn_no")
        .values("party_code", "bill_no", "bill_date", "mrn_no", "mrn_date", "gross_amount", "net_amount")
    )
    party_names = dict(Party.objects.filter(
        party_code__in={r["party_code"] for r in rows if r["party_code"]}
    ).values_list("party_code", "name"))
    mrn_amounts = dict(MrnData.objects.filter(
        mrn_no__in={r["mrn_no"] for r in rows if r["mrn_no"]}
    ).values_list("mrn_no", "amount"))

    result = []
    for r in rows:
        gross = r["gross_amount"]
        if not gross:  # EMPTY(amt) in VFP: null or zero -> fall back to mrn_dat.amount
            gross = mrn_amounts.get(r["mrn_no"]) or Decimal("0")
        result.append({
            "code": (r["party_code"] or "").strip(),
            "party_name": (party_names.get(r["party_code"]) or "").strip(),
            "bill_no": (r["bill_no"] or "").strip(),
            "bill_date": r["bill_date"].isoformat() if r["bill_date"] else "",
            "mrn_no": (r["mrn_no"] or "").strip(),
            "mrn_date": r["mrn_date"].isoformat() if r["mrn_date"] else "",
            "gross_amount": f"{gross:.2f}",
            "net_amount": f"{(r['net_amount'] or 0):.2f}",
        })
    return result


# --- Item Wise Rate List report -----------------------------------------------------------
#
# Old VFP form/report: "ITEM-WISE RATE LIST". Read-only: every imaster row where
#   m_dat >= start_date  AND  m_dat <= end_date  AND  mrn == 'Y'
# grouped/ordered by item code (old VFP: SET ORDER TO icodedate -- (i_code, date) index),
# lines within a group ordered by date. All Item = every item; Single Item narrows to
# one part code.

def item_wise_rate_list(start_date, end_date, part_code=None):
    """[{item_code, item_name, lines: [...]}] -- MRN'd transactions, item-wise."""
    qs = ItemMasterTransaction.objects.filter(
        mrn_date__gte=start_date, mrn_date__lte=end_date, mrn_flag="Y",
    )
    if part_code:
        qs = qs.filter(item_code=part_code.strip().upper())
    rows = list(qs.values("item_code", "party_code", "bill_no", "bill_date", "quantity", "po_qty", "rate"))
    rows.sort(key=lambda r: ((r["item_code"] or ""), r["bill_date"] or date_cls.min))

    parts = {
        p.part_number: p for p in Part.objects.filter(
            part_number__in={r["item_code"] for r in rows if r["item_code"]}
        )
    }
    party_names = dict(Party.objects.filter(
        party_code__in={r["party_code"] for r in rows if r["party_code"]}
    ).values_list("party_code", "name"))
    party_grades = dict(Party.objects.filter(
        party_code__in={r["party_code"] for r in rows if r["party_code"]}
    ).values_list("party_code", "grade"))

    grouped = {}
    for r in rows:
        code = (r["item_code"] or "").strip()
        part = parts.get(code)
        entry = grouped.setdefault(code, {
            "item_code": code,
            "item_name": (part.description_1 if part else "").strip() if part else "",
            "lines": [],
        })
        party_code_ = (r["party_code"] or "").strip()
        entry["lines"].append({
            "code": party_code_,
            "party_name": (party_names.get(party_code_) or "").strip(),
            "grade": (party_grades.get(party_code_) or "").strip(),
            "bill_no": (r["bill_no"] or "").strip(),
            "bill_date": r["bill_date"].isoformat() if r["bill_date"] else "",
            "qty": f"{(r['quantity'] or 0):.3f}",
            "po_qty": f"{(r['po_qty'] or 0):.3f}",
            "rate": f"{(r['rate'] or 0):.2f}",
        })

    return sorted(grouped.values(), key=lambda g: g["item_code"])


# --- Party Wise Rate List report -----------------------------------------------------------
#
# Old VFP form/report: "PARTY-WISE RATE LIST". Same imaster source as Item-Wise Rate List,
# but grouped/ordered by party (old VFP: SET ORDER TO pcodedate -- (p_code, date) index)
# rather than by item.

def party_wise_rate_list(start_date, end_date, party_code=None):
    """[{party_code, party_name, city, grade, lines: [...]}] -- MRN'd transactions, party-wise."""
    qs = ItemMasterTransaction.objects.filter(
        mrn_date__gte=start_date, mrn_date__lte=end_date, mrn_flag="Y",
    )
    if party_code:
        qs = qs.filter(party_code=party_code.strip().upper())
    rows = list(qs.values("item_code", "party_code", "bill_no", "bill_date", "quantity", "po_qty", "rate"))
    rows.sort(key=lambda r: ((r["party_code"] or ""), r["bill_date"] or date_cls.min))

    parts = {
        p.part_number: p for p in Part.objects.filter(
            part_number__in={r["item_code"] for r in rows if r["item_code"]}
        )
    }
    parties = {
        p.party_code: p for p in Party.objects.filter(
            party_code__in={r["party_code"] for r in rows if r["party_code"]}
        )
    }

    grouped = {}
    for r in rows:
        code = (r["party_code"] or "").strip()
        party = parties.get(code)
        entry = grouped.setdefault(code, {
            "party_code": code,
            "party_name": (party.name if party else "").strip() if party else "",
            "city": (party.city if party else "") or "",
            "grade": (party.grade if party else "") or "",
            "lines": [],
        })
        item_code = (r["item_code"] or "").strip()
        part = parts.get(item_code)
        entry["lines"].append({
            "item_code": item_code,
            "item_name": (part.description_1 if part else "").strip() if part else "",
            "bill_no": (r["bill_no"] or "").strip(),
            "bill_date": r["bill_date"].isoformat() if r["bill_date"] else "",
            "qty": f"{(r['quantity'] or 0):.3f}",
            "po_qty": f"{(r['po_qty'] or 0):.3f}",
            "rate": f"{(r['rate'] or 0):.2f}",
        })

    return sorted(grouped.values(), key=lambda g: g["party_code"])


# --- Party Pending Order Letter -------------------------------------------------------------
#
# Old VFP form/report: "PARTY PENDING ORDER LETTER". A formal letter to one party listing
# its still-pending PO lines. Legacy condition (no adj check here, unlike the tabular
# Pending P.O. report):
#   p_code == selected party  AND  stk_qty - rec_qty > 0
# sorted by order date ascending (old VFP: SET ORDER TO date).

def party_pending_order_letter(party_code, run_date):
    """{"party": {...}, "lines": [...]} for one party's still-pending PO lines."""
    party = Party.objects.filter(party_code=party_code.strip().upper()).first()
    if not party:
        return None
    rows = list(
        PurchaseOrderItem.objects.filter(party_code=party.party_code)
        .values("div", "po_no", "part_code", "order_date", "quantity", "received_qty", "despatch_date")
    )
    rows = [r for r in rows if (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0")) > 0]
    rows.sort(key=lambda r: r["order_date"] or date_cls.min)

    part_names = dict(Part.objects.filter(
        part_number__in={r["part_code"] for r in rows if r["part_code"]}
    ).values_list("part_number", "description_1"))

    lines = []
    for r in rows:
        delay_days = (run_date - r["despatch_date"]).days if r["despatch_date"] else None
        lines.append({
            "ord_no": f"{(r['div'] or '').strip()} {r['po_no']}",
            "div": (r["div"] or "").strip(),  # for the WhatsApp share-link call -- not shown on screen
            "po_no": r["po_no"],
            "ord_date": r["order_date"].isoformat() if r["order_date"] else "",
            "item_code": (r["part_code"] or "").strip(),
            "item_name": (part_names.get(r["part_code"]) or "").strip(),
            "pending_qty": f"{(r['quantity'] or Decimal('0')) - (r['received_qty'] or Decimal('0')):.3f}",
            "despatch_date": r["despatch_date"].isoformat() if r["despatch_date"] else "",
            "delay_days": delay_days,
        })

    return {
        "party": {
            "code": party.party_code,
            "name": (party.name or "").strip(),
            "address_1": (party.address_1 or "").strip(),
            "address_2": (party.address_2 or "").strip(),
            "address_3": (party.address_3 or "").strip(),
            "city": (party.city or "").strip(),
            "mobile": (party.mobile_1 or "").strip(),
        },
        "lines": lines,
    }


def get_pending_letter_share_token(party_code, run_date):
    """Token for a public, no-login link to one party's Pending PO Reminder
    letter PDF (for sharing over WhatsApp) -- reuses one already issued for
    this party+run date if it's still valid, same convention as the PO
    share link above."""
    if not party_pending_order_letter(party_code, run_date):
        return None
    return PendingLetterShareLink.get_or_create_for(party_code, run_date).token


def get_pending_letter_by_share_token(token):
    """The (party_code, run_date) a public reminder share link's token points
    to, or (None, None) if the token is unknown, expired, or revoked."""
    link = PendingLetterShareLink.objects.filter(token=token).first()
    if not link or not link.is_valid():
        return None, None
    return link.party_code, link.run_date


# --- Itemwise Party List report ------------------------------------------------------------
#
# Old VFP form/report: "ITEMWISE PARTY LIST". For ONE selected part, look at its four
# supplier/rate slots (party1/rate1 .. party4/rate4) and, for each slot whose party code
# resolves to a real party, output one row. Never mixes rates across slots; a blank or
# unknown supplier code in a slot is simply skipped (old VFP: SEEK ... IF FOUND()).

def itemwise_party_list(part_code):
    """{"part": {code, name}, "rows": [...]} or None if the part doesn't exist."""
    part = Part.objects.filter(part_number=part_code.strip().upper()).first()
    if not part:
        return None

    slot_codes = [
        (part.supplier_1 or "").strip(), (part.supplier_2 or "").strip(),
        (part.supplier_3 or "").strip(), (part.supplier_4 or "").strip(),
    ]
    slot_rates = [part.rate_1, part.rate_2, part.rate_3, part.rate_4]
    parties = {
        p.party_code: p for p in Party.objects.filter(party_code__in={c for c in slot_codes if c})
    }

    rows = []
    for code, rate in zip(slot_codes, slot_rates):
        if not code:
            continue
        party = parties.get(code)
        if not party:  # SEEK ... IF FOUND() -- skip a supplier code not in Party Master
            continue
        rows.append({
            "party_code": code,
            "party_name": (party.name or "").strip(),
            "city": (party.city or "").strip(),
            "grade": (party.grade or "").strip(),
            "rate": f"{(rate or 0):.2f}",
        })

    return {
        "part": {"code": part.part_number, "name": (part.description_1 or "").strip()},
        "rows": rows,
    }


# --- Party Wise Item List report -----------------------------------------------------------
#
# Old VFP form/report: "PARTY WISE ITEM LIST" (pwil.PRN). Inverse of Itemwise Party List
# above: for ONE selected party, scan every part and check its four supplier slots
# (party1/rate1 .. party4/rate4) for a match against the selected party code, using
# whichever slot's rate corresponds. Old VFP used a DO CASE (first match wins per part,
# never mixes slots), ordered by i_code (Part.part_number).

def party_wise_item_list(party_code):
    """{"party": {code, name, grade}, "rows": [...]} or None if the party doesn't exist."""
    party = Party.objects.filter(party_code=party_code.strip().upper()).first()
    if not party:
        return None

    rows = []
    for part in Part.objects.order_by("part_number"):
        slots = [
            ((part.supplier_1 or "").strip(), part.rate_1),
            ((part.supplier_2 or "").strip(), part.rate_2),
            ((part.supplier_3 or "").strip(), part.rate_3),
            ((part.supplier_4 or "").strip(), part.rate_4),
        ]
        for code, rate in slots:  # DO CASE: first matching slot wins, never mixes slots
            if code == party.party_code:
                rows.append({
                    "code": part.part_number,
                    "name": (part.description_1 or "").strip(),
                    "rate": f"{(rate or 0):.2f}",
                })
                break

    return {
        "party": {
            "code": party.party_code,
            "name": (party.name or "").strip(),
            "grade": (party.grade or "").strip(),
        },
        "rows": rows,
    }


# --- Pending Purchase Order Adjustment ------------------------------------------------------
#
# Old VFP form: PENDING PURCHASE ORDER ADJUSTMENT. For a selected party, list every PO
# line still pending (stk_qty - rec_qty > 0) and not yet adjusted (adj # 'Y'), and let the
# user write a value into each line's own `adj` field. A line is identified by
# (div, po_no, part_code, party_code) together -- the real ``order`` table has no key,
# so, like LOCATE in the old code, only the first matching row is ever touched.

class PurchaseOrderAdjustmentError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def pending_po_adjustment(party_code):
    """{"party": {code, name}, "rows": [...]} or None if the party doesn't exist."""
    party = Party.objects.filter(party_code=party_code.strip().upper()).first()
    if not party:
        return None

    lines = list(
        PurchaseOrderItem.objects.filter(party_code=party.party_code)
        .exclude(adjusted="Y")
        .order_by("order_date", "po_no")
        .values("div", "po_no", "order_date", "part_code", "quantity", "received_qty", "adjusted")
    )
    codes = {l["part_code"] for l in lines if l["part_code"]}
    names = dict(Part.objects.filter(part_number__in=codes).values_list("part_number", "description_1"))

    rows = []
    for l in lines:
        qty = l["quantity"] or Decimal("0")
        rec = l["received_qty"] or Decimal("0")
        pending = qty - rec
        if pending <= 0:
            continue
        rows.append({
            "po_no": (l["po_no"] or "").strip(),
            "div": (l["div"] or "").strip(),
            "order_date": l["order_date"].isoformat() if l["order_date"] else "",
            "part_code": (l["part_code"] or "").strip(),
            "item_name": (names.get(l["part_code"]) or "").strip(),
            "qty_ordered": f"{qty:.3f}",
            "qty_received": f"{rec:.3f}",
            "pending": f"{pending:.3f}",
            "adj": (l["adjusted"] or "").strip(),
        })

    return {
        "party": {"code": party.party_code, "name": (party.name or "").strip()},
        "rows": rows,
    }


def save_po_adjustments(party_code, rows):
    """CONFIRM: write each row's ``adj`` value onto the one matching, still-open PO
    line (div + po_no + part_code + party_code), mirroring the old LOCATE/RLOCK/REPLACE
    -- never more than one row per entry, never a row already marked 'Y'."""
    _require_writes()
    party_code = (party_code or "").strip().upper()
    if not party_code:
        raise PurchaseOrderAdjustmentError("Select a party first.", {"party_code": "Select a party."})
    if not Party.objects.filter(party_code=party_code).exists():
        raise PurchaseOrderAdjustmentError("Party not found.", {"party_code": "Party not found."})
    if not isinstance(rows, list) or not rows:
        raise PurchaseOrderAdjustmentError("Nothing to save.", {"": "Enter at least one adjustment."})

    updated = 0
    skipped = []
    with transaction.atomic(using=PurchaseOrderItem.objects.db):
        for row in rows:
            po_no = str((row or {}).get("po_no", "")).strip()
            div = str((row or {}).get("div", "")).strip()
            part_code = str((row or {}).get("part_code", "")).strip().upper()
            adj = str((row or {}).get("adj", "")).strip()[:1]
            if not po_no or not part_code or not adj:
                continue
            # The real ``order`` table has no key at all (not even a real ``id`` column --
            # the model's ``id`` is a Django-only surrogate), so a targeted single-row
            # UPDATE by primary key isn't possible here. Instead, update every row still
            # matching this (div, po_no, part_code, party_code) tuple that isn't already
            # adjusted -- normally exactly one row, per the model's own docstring.
            changed = (
                PurchaseOrderItem.objects.filter(
                    po_no=po_no, div=div, part_code=part_code, party_code=party_code,
                )
                .exclude(adjusted="Y")
                .update(adjusted=adj)
            )
            if changed:
                updated += changed
            else:
                skipped.append(f"{po_no}/{part_code}")

    return {"updated": updated, "skipped": skipped}

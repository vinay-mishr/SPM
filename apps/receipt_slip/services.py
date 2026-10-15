"""
Single Receipt Slip business logic. Old VFP form: SINGLE RECEIPT SLIP / rmis1.

Confirmed rules from the legacy save code (D:/SPM/rmis1.SCT):
* Each received line is an imaster row: bill_no = receipt challan, bill date,
  i_code, qty, inv_rt (invoice rate), REMAK, stts='R', recv='Y'.
* Stock RISES: partmst.cur_stk += qty for every line. Delete and the reverse half
  of a modify take it back down by the same quantities.
* Header is rmis_mst (mis_no, mis_dt, remk, remk1, ttype=' ').
* Counter: inv_no.rmis_no -- on Add it must be at least the number entered.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction

from apps.bom.services import search_parts  # noqa: F401 -- re-exported for the views
from apps.parts.models import Part
from apps.purchase_orders.models import ItemMasterTransaction

from .models import InvNo, ReceiptSlip

PERMISSION = "receipt_slip.change_receipt_slip"
DEFAULT_DIV = "SP"


class ReceiptSlipError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise ReceiptSlipError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _qty(value):
    return f"{(value or 0):.3f}"


def _rate(value):
    return f"{(value or 0):.2f}"


def list_receipt_slips(start_date, end_date):
    rows = list(
        ReceiptSlip.objects.filter(mis_date__gte=start_date, mis_date__lte=end_date)
        .filter(models.Q(ttype__isnull=True) | models.Q(ttype__in=["", " "]))
        .values("mis_no", "mis_date")
    )
    unames = {}
    for line in ItemMasterTransaction.objects.filter(
        status="R", received_flag="Y", bill_no__in=[r["mis_no"] for r in rows]
    ).values("bill_no", "uname"):
        if line["uname"] and not unames.get(line["bill_no"]):
            unames[line["bill_no"]] = line["uname"]
    result = [
        {"key": r["mis_no"], "mis_no": r["mis_no"], "mis_date": r["mis_date"].isoformat() if r["mis_date"] else "",
         "uname": _clean(unames.get(r["mis_no"]))}
        for r in rows
    ]
    result.sort(key=lambda r: (r["mis_date"], r["mis_no"]), reverse=True)
    return result


def _first_value(queryset):
    rows = list(queryset[:1])
    return rows[0] if rows else None


def _receipt_lines(mis_no):
    return ItemMasterTransaction.objects.filter(bill_no=mis_no, status="R", received_flag="Y")


def _highest_existing_receipt_no():
    line_numbers = ItemMasterTransaction.objects.filter(status="R", received_flag="Y").exclude(bill_no="") \
        .values_list("bill_no", flat=True)
    numbers = [int(n) for n in line_numbers if str(n).strip().isdigit()]
    numbers += [int(n) for n in ReceiptSlip.objects.values_list("mis_no", flat=True) if str(n).strip().isdigit()]
    return max(numbers) if numbers else 0


def _current_counter():
    value = _first_value(InvNo.objects.values_list("next_receipt_no", flat=True))
    return max(int(value) if value is not None else 0, _highest_existing_receipt_no())


def next_receipt_no():
    return str(_current_counter() + 1)


def _allocate_receipt_no():
    value = _first_value(InvNo.objects.select_for_update().values_list("next_receipt_no", flat=True))
    new_no = max(int(value) if value is not None else 0, _highest_existing_receipt_no()) + 1
    InvNo.objects.update(next_receipt_no=new_no)
    return str(new_no)


def get_receipt_slip(mis_no):
    header = ReceiptSlip.objects.filter(mis_no=mis_no).first()
    if not header:
        return None
    lines = list(_receipt_lines(mis_no).values("item_code", "quantity", "invoice_rate", "remarks", "uname"))
    part_names = dict(Part.objects.filter(
        part_number__in={r["item_code"] for r in lines if r["item_code"]}
    ).values_list("part_number", "description_1"))
    return {
        "mis_no": header.mis_no,
        "mis_date": header.mis_date.isoformat() if header.mis_date else "",
        "remarks": _clean(header.remarks),
        "uname": _clean(next((r["uname"] for r in lines if r["uname"]), "")),
        "items": [
            {
                "part_code": _clean(r["item_code"]),
                "part_name": _clean(part_names.get(r["item_code"])),
                "qty": _qty(r["quantity"]),
                "invoice_rate": _rate(r["invoice_rate"]),
                "remarks": _clean(r["remarks"]),
            }
            for r in lines
        ],
    }


def _validate_items(items):
    if not isinstance(items, list) or not items:
        raise ReceiptSlipError("Add at least one item.", {"": "Add at least one item."})
    codes = {(it.get("part_code") or "").strip().upper() for it in items if (it or {}).get("part_code")}
    known = set(Part.objects.filter(part_number__in=codes).values_list("part_number", flat=True))
    cleaned = []
    for row_no, it in enumerate(items, start=1):
        part_code = (it.get("part_code") or "").strip().upper()
        if not part_code:
            raise ReceiptSlipError("Every row needs an item.", {"": f"Row {row_no}: select an item."})
        if part_code not in known:
            raise ReceiptSlipError("Unknown item.", {"": f"Row {row_no}: '{part_code}' isn't in the Item Master."})
        try:
            qty = Decimal(str(it.get("qty") or "0"))
            rate = Decimal(str(it.get("invoice_rate") or "0"))
        except Exception:
            raise ReceiptSlipError("Invalid number.", {"": f"Row {row_no}: enter a valid quantity and rate."})
        if qty <= 0:
            raise ReceiptSlipError("Invalid quantity.", {"": f"Row {row_no}: quantity must be more than 0."})
        if rate < 0:
            raise ReceiptSlipError("Invalid rate.", {"": f"Row {row_no}: invoice rate can't be negative."})
        cleaned.append({"item_code": part_code, "quantity": qty, "invoice_rate": rate,
                        "remarks": (it.get("remarks") or "").strip()[:40]})
    return cleaned


def _apply_stock(lines, sign):
    """Legacy: partmst.cur_stk rises by each received qty (sign=+1 on save), and
    falls back by it on delete / modify reversal (sign=-1)."""
    for line in lines:
        Part.objects.filter(part_number=line["item_code"]).update(
            current_stock=models.F("current_stock") + sign * line["quantity"],
        )


def _old_lines(mis_no):
    return [{"item_code": r["item_code"], "quantity": r["quantity"] or Decimal("0")}
            for r in _receipt_lines(mis_no).values("item_code", "quantity")]


def save_receipt_slip(mis_date, items, remarks="", key=None, username="", chl_no=""):
    _require_writes()
    if not mis_date:
        raise ReceiptSlipError("Fix the highlighted fields.", {"mis_date": "Date is required."})
    cleaned = _validate_items(items)

    with transaction.atomic(using=ReceiptSlip.objects.db):
        if key:
            mis_no = key
            header = ReceiptSlip.objects.filter(mis_no=mis_no).first()
            if not header:
                raise ReceiptSlipError("This receipt no longer exists.")
            _apply_stock(_old_lines(mis_no), sign=-1)
            _receipt_lines(mis_no).delete()
        else:
            typed = (chl_no or "").strip()
            if typed:
                if not typed.isdigit():
                    raise ReceiptSlipError("Enter a numeric challan no.", {"mis_no": "Challan no must be a number."})
                if ReceiptSlip.objects.filter(mis_no=typed).exists() or _receipt_lines(typed).exists():
                    raise ReceiptSlipError("MIS NO ALREADY EXIST", {"mis_no": "This challan number already exists."})
                mis_no = typed
                value = _first_value(InvNo.objects.select_for_update().values_list("next_receipt_no", flat=True))
                if value is None or int(value) < int(typed):
                    InvNo.objects.update(next_receipt_no=int(typed))
            else:
                mis_no = _allocate_receipt_no()
            header = ReceiptSlip(mis_no=mis_no)

        header.mis_date = mis_date
        header.remarks = remarks[:40]
        header.ttype = " "
        header.save()

        ItemMasterTransaction.objects.bulk_create([
            ItemMasterTransaction(
                bill_no=mis_no, bill_date=mis_date, item_code=item["item_code"],
                quantity=item["quantity"], invoice_rate=item["invoice_rate"], remarks=item["remarks"],
                status="R", received_flag="Y", uname=username[:10], div=DEFAULT_DIV,
            )
            for item in cleaned
        ])
        _apply_stock(cleaned, sign=+1)
    return {"mis_no": mis_no}


def delete_receipt_slip(mis_no):
    _require_writes()
    with transaction.atomic(using=ReceiptSlip.objects.db):
        header = ReceiptSlip.objects.filter(mis_no=mis_no).first()
        if not header:
            raise ReceiptSlipError("This receipt no longer exists.")
        _apply_stock(_old_lines(mis_no), sign=-1)
        _receipt_lines(mis_no).delete()
        header.delete()
        current = _first_value(InvNo.objects.select_for_update().values_list("next_receipt_no", flat=True))
        if current is not None and str(int(current)) == str(mis_no):
            InvNo.objects.update(next_receipt_no=int(mis_no) - 1)


# --- Single Receipt Report -----------------------------------------------------------
#
# Old VFP report: "SINGLE RECEIPT REPORT". A flat scan of imaster filtered on
#   date >= start_date  AND  date <= end_date  AND  recv = 'Y'
# ITEM DESC / UNIT come from the Item Master (a.ides / a.uom), as in the issue report.

def single_receipt_report(start_date, end_date):
    rows = list(
        ItemMasterTransaction.objects.filter(
            bill_date__gte=start_date, bill_date__lte=end_date, received_flag="Y",
        ).values("bill_no", "bill_date", "item_code", "quantity", "invoice_rate")
    )
    rows.sort(key=lambda r: (r["bill_date"] or start_date, r["bill_no"] or ""))
    parts = {
        p.part_number: p for p in Part.objects.filter(
            part_number__in={r["item_code"] for r in rows if r["item_code"]}
        )
    }
    result = []
    for r in rows:
        part = parts.get((r["item_code"] or "").strip())
        result.append({
            "challan_no": _clean(r["bill_no"]),
            "date": r["bill_date"].isoformat() if r["bill_date"] else "",
            "item_code": _clean(r["item_code"]),
            "item_name": _clean(part.description_1) if part else "",
            "unit": _clean(part.unit) if part else "",
            "qty": f"{(r['quantity'] or 0):.3f}",
            "inv_rate": f"{(r['invoice_rate'] or 0):.2f}",
        })
    return result


def stock_report(start_date, end_date):
    """VFP STOCK RECEIPT REPORT: imaster lines with stts 'P' or 'R' in the date range, by date."""
    rows = list(
        ItemMasterTransaction.objects.filter(
            bill_date__gte=start_date, bill_date__lte=end_date, status__in=["P", "R"],
        ).values("bill_no", "bill_date", "item_code", "quantity").order_by("bill_date", "bill_no")
    )
    parts = {
        p.part_number: p for p in Part.objects.filter(
            part_number__in={r["item_code"] for r in rows if r["item_code"]}
        )
    }
    result = []
    for n, r in enumerate(rows, start=1):
        part = parts.get((r["item_code"] or "").strip())
        result.append({
            "sno": n,
            "bill_no": _clean(r["bill_no"]),
            "date": r["bill_date"].isoformat() if r["bill_date"] else "",
            "item_name": _clean(part.description_1) if part else "",
            "qty": f"{(r['quantity'] or 0):.3f}",
        })
    return result


def current_stock_report(run_date):
    """VFP CURRENT STOCK: opening stock + S/I receipts - P/A/R issues dated on or before run_date."""
    moves = {}
    for row in ItemMasterTransaction.objects.filter(bill_date__lte=run_date, status__in=["S", "I", "P", "A", "R"]).values(
            "item_code", "status", "quantity"):
        code = (row["item_code"] or "").strip()
        qty = row["quantity"] or 0
        sign = 1 if row["status"] in ("S", "I") else -1
        moves[code] = moves.get(code, 0) + sign * qty
    rows = []
    for p in Part.objects.order_by("part_number"):
        balance = (p.opening_stock or 0) + moves.get((p.part_number or "").strip(), 0)
        rows.append({
            "code": _clean(p.part_number),
            "name": _clean(p.description_1),
            "qty": f"{balance:.3f}",
        })
    return rows

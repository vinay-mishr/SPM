"""
Single Issue Slip business logic. Old VFP form/file: SINGLE ISSUE SLIP / mis1.

Line items live in the existing ``imaster`` table (``apps.purchase_orders.models.
ItemMasterTransaction``) -- same shared table MRN Entry's items live in (see
this app's models.py for how that was confirmed against real data).

No existing code anywhere in this project automatically adjusts
``Part.current_stock`` on any save/modify/delete (MRN Entry, the other module
that already issues/receives real stock, only ever updates PO received
quantities -- never touches ``current_stock``), and the supplied legacy VFP
code for this screen's actual CONFIRM/save routine was never provided (only
its navigation/password-prompt code was). Per this project's own "don't
invent stock behavior" convention for ambiguous legacy logic, this module
does NOT touch ``Part.current_stock`` -- it only saves the slip and its line
items. If a real stock effect is wanted, confirm the exact rule against the
legacy save code before adding it.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction

from apps.bom.services import search_parts  # noqa: F401 -- re-exported for the views
from apps.parts.models import Part
from apps.purchase_orders.models import ItemMasterTransaction

from .models import InvNo, IssueSlip

PERMISSION = "issue_slip.change_issue_slip"
DEFAULT_DIV = "SP"


class IssueSlipError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise IssueSlipError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _qty(value):
    return f"{(value or 0):.3f}"


# --- Listing ------------------------------------------------------------------------

def list_issue_slips(start_date, end_date):
    """Issue slips in the given date range -- old VFP: SCAN FOR mis_dt>=.. AND
    mis_dt<=.. AND TTYPE=' '."""
    rows = list(
        IssueSlip.objects.filter(mis_date__gte=start_date, mis_date__lte=end_date)
        .filter(models.Q(ttype__isnull=True) | models.Q(ttype__in=["", " "]))
        .values("mis_no", "mis_date")
    )
    unames = {}
    for line in ItemMasterTransaction.objects.filter(
        single_issue_flag="Y", status="I", bill_no__in=[r["mis_no"] for r in rows]
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
    """queryset[0] instead of .first() -- .first() adds "ORDER BY pk" whenever a
    queryset isn't already explicitly ordered (even .order_by() doesn't stop it),
    and InvNo's "id" is a Django-only surrogate the real table has no matching
    column for (same convention as apps.mrn.services._first_value)."""
    rows = list(queryset[:1])
    return rows[0] if rows else None


def _highest_existing_issue_no():
    """The counter's own column (inv_no.mis_no) has never been initialized in
    this environment (NULL), so the highest challan number already in use is
    scanned from the issue lines and headers before numbering a new slip --
    same defensive convention as apps.purchase_orders.services.next_po_number()."""
    numbers = [int(n) for n in ItemMasterTransaction.objects.filter(single_issue_flag="Y", status="I")
               .exclude(bill_no="").values_list("bill_no", flat=True) if str(n).strip().isdigit()]
    numbers += [int(n) for n in IssueSlip.objects.values_list("mis_no", flat=True) if str(n).strip().isdigit()]
    return max(numbers) if numbers else 0


def _current_issue_counter():
    # NULL on the shared inv_no row means "no issue slip has ever been
    # numbered through this counter yet" -- see _highest_existing_issue_no()
    # for why that alone isn't trusted blindly.
    value = _first_value(InvNo.objects.values_list("next_issue_no", flat=True))
    return max(int(value) if value is not None else 0, _highest_existing_issue_no())


def next_issue_no():
    """A preview of the likely next challan no, for the Add form to show before
    the user has saved anything -- NOT the authoritative allocation (that only
    happens, locked, inside save_issue_slip() itself)."""
    return str(_current_issue_counter() + 1)


def _allocate_issue_no():
    """The real, locked allocation: select_for_update() on the single counter
    row blocks any other save (Add or Modify-that-reuses-Add's-flow) started
    concurrently until this transaction commits, so two users can't both end up
    saving the same challan no. .update() (not fetch-a-row-then-.save()) is
    what avoids the same "id" problem on the write side."""
    value = _first_value(InvNo.objects.select_for_update().values_list("next_issue_no", flat=True))
    current = max(int(value) if value is not None else 0, _highest_existing_issue_no())
    new_no = current + 1
    InvNo.objects.update(next_issue_no=new_no)
    return str(new_no)


def _issue_slip_lines(mis_no):
    """The legacy issue lines: imaster rows with this challan (bill_no), sing='Y'
    and stts='I'. Those two flags keep MRN and other rows that also use bill_no
    (invoice numbers) out of this set."""
    return ItemMasterTransaction.objects.filter(bill_no=mis_no, single_issue_flag="Y", status="I")


def get_issue_slip(mis_no):
    """One issue slip's header + its line items (from imaster -- see this
    app's models.py docstring)."""
    header = IssueSlip.objects.filter(mis_no=mis_no).first()
    if not header:
        return None
    items = list(_issue_slip_lines(mis_no).values("item_code", "quantity", "remarks", "uname"))
    part_names = dict(Part.objects.filter(
        part_number__in={r["item_code"] for r in items if r["item_code"]}
    ).values_list("part_number", "description_1"))
    return {
        "mis_no": header.mis_no,
        "mis_date": header.mis_date.isoformat() if header.mis_date else "",
        "remarks": _clean(header.remarks),
        "uname": _clean(next((r["uname"] for r in items if r["uname"]), "")),
        "items": [
            {
                "part_code": _clean(r["item_code"]),
                "part_name": _clean(part_names.get(r["item_code"])),
                "qty_issued": _qty(r["quantity"]),
                "remarks": _clean(r["remarks"]),
            }
            for r in items
        ],
    }


def _validate_items(items):
    if not isinstance(items, list) or not items:
        raise IssueSlipError("Add at least one item.", {"": "Add at least one item."})
    codes = {(it.get("part_code") or "").strip().upper() for it in items if (it or {}).get("part_code")}
    known = set(Part.objects.filter(part_number__in=codes).values_list("part_number", flat=True))
    cleaned = []
    for row_no, it in enumerate(items, start=1):
        part_code = (it.get("part_code") or "").strip().upper()
        if not part_code:
            raise IssueSlipError("Every row needs an item.", {"": f"Row {row_no}: select an item."})
        if part_code not in known:
            raise IssueSlipError("Unknown item.", {"": f"Row {row_no}: '{part_code}' isn't in the Item Master."})
        try:
            qty = Decimal(str(it.get("qty_issued") or "0"))
        except Exception:
            raise IssueSlipError("Invalid quantity.", {"": f"Row {row_no}: enter a valid quantity."})
        if qty <= 0:
            raise IssueSlipError("Invalid quantity.", {"": f"Row {row_no}: quantity issued must be more than 0."})
        cleaned.append({
            "item_code": part_code, "quantity": qty, "remarks": (it.get("remarks") or "").strip()[:40],
        })
    return cleaned


def _apply_stock(lines, sign):
    """Legacy: partmst.stock reduced by each issued qty on save (sign=-1), and
    restored on delete/modify-reversal (sign=+1). Stock is decimal(10,0) in the
    legacy table, so fractional quantities are stored rounded, as the old
    software already does."""
    for line in lines:
        Part.objects.filter(part_number=line["item_code"]).update(
            stock_balance=models.F("stock_balance") + sign * line["quantity"],
        )


def save_issue_slip(mis_date, items, remarks="", key=None, username=""):
    """ADD (key is None) or MODIFY (key given) one issue slip, in one transaction:
    the header in mis_mst, each line in imaster (bill_no = challan, sing='Y',
    stts='I'), and partmst.stock reduced by the issued quantities. MODIFY first
    restores the old lines' stock, then applies the new quantities, so stock is
    never deducted twice."""
    _require_writes()
    if not mis_date:
        raise IssueSlipError("Fix the highlighted fields.", {"mis_date": "Date is required."})
    cleaned = _validate_items(items)

    with transaction.atomic(using=IssueSlip.objects.db):
        if key:
            mis_no = key
            header = IssueSlip.objects.filter(mis_no=mis_no).first()
            if not header:
                raise IssueSlipError("This issue slip no longer exists.")
            old_lines = [
                {"item_code": r["item_code"], "quantity": r["quantity"] or Decimal("0")}
                for r in _issue_slip_lines(mis_no).values("item_code", "quantity")
            ]
            _apply_stock(old_lines, sign=+1)
            _issue_slip_lines(mis_no).delete()
        else:
            mis_no = _allocate_issue_no()
            if IssueSlip.objects.filter(mis_no=mis_no).exists():
                raise IssueSlipError("This challan number is already in use.")
            header = IssueSlip(mis_no=mis_no)

        header.mis_date = mis_date
        header.remarks = remarks[:40]
        header.ttype = " "
        header.save()

        ItemMasterTransaction.objects.bulk_create([
            ItemMasterTransaction(
                bill_no=mis_no, bill_date=mis_date, item_code=item["item_code"],
                quantity=item["quantity"], remarks=item["remarks"], single_issue_flag="Y",
                status="I", uname=username[:10], div=DEFAULT_DIV,
            )
            for item in cleaned
        ])
        _apply_stock(cleaned, sign=-1)

    return {"mis_no": mis_no}


def delete_issue_slip(mis_no):
    """DELETE: restores each line's stock, removes its imaster rows and the
    header, in one transaction. The counter steps back only when this was the
    latest number issued (same guard as the legacy form)."""
    _require_writes()
    with transaction.atomic(using=IssueSlip.objects.db):
        header = IssueSlip.objects.filter(mis_no=mis_no).first()
        if not header:
            raise IssueSlipError("This issue slip no longer exists.")
        old_lines = [
            {"item_code": r["item_code"], "quantity": r["quantity"] or Decimal("0")}
            for r in _issue_slip_lines(mis_no).values("item_code", "quantity")
        ]
        _apply_stock(old_lines, sign=+1)
        _issue_slip_lines(mis_no).delete()
        header.delete()
        current = _first_value(InvNo.objects.select_for_update().values_list("next_issue_no", flat=True))
        if current is not None and str(int(current)) == str(mis_no):
            InvNo.objects.update(next_issue_no=int(mis_no) - 1)


# --- Single Issue Report -------------------------------------------------------------
#
# Old VFP report: "SINGLE ISSUE REPORT". A flat scan of imaster -- the same rows
# the Single Issue Slip saves -- filtered on:
#   date >= start_date  AND  date <= end_date  AND  sing = 'Y'
# ITEM DESC/UNIT come from the Item Master (a.ides/a.uom), not from any column
# on imaster itself (confirmed against Part.description_1/Part.unit's own
# db_column mappings, "ides"/"uom", matching the legacy alias 'a' exactly).

def single_issue_report(start_date, end_date):
    """[{challan_no, date, item_code, item_name, unit, qty}, ...] -- flat rows,
    ordered by date then challan no (old VFP: SET ORDER TO idate)."""
    rows = list(
        ItemMasterTransaction.objects.filter(
            bill_date__gte=start_date, bill_date__lte=end_date, single_issue_flag="Y",
        ).values("bill_no", "bill_date", "item_code", "quantity")
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
        })
    return result

"""
MRN Entry business logic. Old VFP form: MRN ENTRY / grn5.

Line items live in the existing ``imaster`` table (``apps.purchase_orders.models.
ItemMasterTransaction``) -- confirmed against real data (MRN "7"'s 4 bearing
lines are 4 rows there with ``mrn_no="7"``), not in a new table. An earlier
version of this module wrongly assumed no such table existed and created one;
that's corrected here -- see ItemMasterTransaction's own docstring.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import DecimalField, F, Value
from django.db.models.functions import Coalesce

from apps.bom.services import search_parts  # noqa: F401 -- re-exported for the views
from apps.creditor_outstanding.services import search_parties  # noqa: F401 -- re-exported
from apps.parties.models import Party
from apps.items.models import Item
from apps.parts.models import Part
from apps.purchase_orders.models import ItemMasterTransaction, PurchaseOrderItem
from apps.purchase_orders.services import last_rate as last_rate_for  # noqa: F401 -- re-exported for the views

from .models import InvNo, MrnAuditLog, MrnData, MrnShareLink


def _audit(div, mrn_no, action, username):
    MrnAuditLog.objects.create(div=(div or "")[:2], mrn_no=mrn_no, action=action, username=(username or "")[:150])

PERMISSION = "mrn.change_mrn"
DEFAULT_DIV = "SP"


class MrnError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise MrnError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _money(value):
    return f"{(value or 0):.2f}"


def _qty(value):
    return f"{(value or 0):.3f}"


def _party_names_and_cities(codes):
    rows = Party.objects.filter(party_code__in=set(codes)).values_list("party_code", "name", "city", "mobile_1")
    names = {code: name for code, name, _, _ in rows}
    cities = {code: city for code, _, city, _ in rows}
    mobiles = {code: mobile for code, _, _, mobile in rows}
    return names, cities, mobiles


# --- Listing ------------------------------------------------------------------------

def list_mrns(start_date, end_date):
    """MRNs with a non-empty MRN no, in the given date range, newest first --
    old VFP: SCAN FOR mrn_dt>=.. AND mrn_dt<=.. AND !EMPTY(mrn_no)."""
    rows = list(
        MrnData.objects.filter(mrn_date__gte=start_date, mrn_date__lte=end_date)
        .exclude(mrn_no__isnull=True).exclude(mrn_no="")
        .values("div", "mrn_no", "mrn_date", "bill_date", "bill_no", "party_code", "ac_transferred", "mrn_closed", "uname")
    )
    names, cities, mobiles = _party_names_and_cities(r["party_code"] for r in rows)
    result = []
    for r in rows:
        party = (r["party_code"] or "").strip()
        result.append({
            "key": f"{(r['div'] or '').strip()}|{r['mrn_no']}",
            "div": (r["div"] or "").strip(),
            "mrn_no": r["mrn_no"],
            "mrn_date": r["mrn_date"].isoformat() if r["mrn_date"] else "",
            "bill_date": r["bill_date"].isoformat() if r["bill_date"] else "",
            "bill_no": _clean(r["bill_no"]),
            "party_code": party,
            "party_name": _clean(names.get(party))[:30],
            "city": _clean(cities.get(party))[:15],
            "party_mobile": _clean(mobiles.get(party)),
            "ac_transferred": _clean(r["ac_transferred"]) or "N",
            "mrn_closed": _clean(r["mrn_closed"]) or "N",
            "uname": _clean(r["uname"]),
        })
    result.sort(key=lambda r: (r["mrn_date"], r["mrn_no"]), reverse=True)
    return result


def _first_value(queryset):
    """queryset[0] instead of .first() -- .first() adds "ORDER BY pk" whenever
    a queryset isn't already explicitly ordered (even .order_by() doesn't stop
    it), and InvNo's "id" is a Django-only surrogate the real table has no
    matching column for (see PurchaseOrderItem's own docstring for this
    convention), so that ORDER BY fails. A plain slice never adds one."""
    rows = list(queryset[:1])
    return rows[0] if rows else None


def _current_mrn_counter():
    value = _first_value(InvNo.objects.values_list("next_mrn_no", flat=True))
    if value is None:
        raise MrnError("The document numbering counter row is missing.")
    return int(value)


def next_mrn_no():
    """A preview of the likely next MRN number, for the Add form to show before
    the user has saved anything -- NOT the authoritative allocation (that only
    happens, locked, inside save_mrn() itself, so two users opening Add at the
    same moment can't both end up saving the same number)."""
    return str(_current_mrn_counter() + 1)


def _allocate_mrn_no():
    """The real, locked allocation: select_for_update() on the single counter
    row (old VFP's FLOCK() on the same row, same idea) means whoever gets the
    lock first reads-and-bumps it atomically, so no two saves can ever receive
    the same MRN number. Caller must already be inside a transaction on the
    same database as InvNo (true here -- MrnData and InvNo are both "legacy").
    .update() (not fetch-a-row-then-.save()) is what avoids the same "id"
    problem on the write side."""
    value = _first_value(InvNo.objects.select_for_update().values_list("next_mrn_no", flat=True))
    if value is None:
        raise MrnError("The document numbering counter row is missing.")
    new_no = int(value) + 1
    InvNo.objects.update(next_mrn_no=new_no)
    return str(new_no)


def _mrn_items(div, mrn_no):
    return list(
        ItemMasterTransaction.objects.filter(mrn_no=mrn_no).values(
            "item_code", "po_div", "po_no", "po_date", "po_qty", "size", "unit",
            "quantity", "qty_rejected", "rate", "discount_percent", "discount_amount",
            "gst_percent", "amount",
        )
    )


def get_mrn_share_token(div, mrn_no):
    """Token for a public, no-login link to this MRN's PDF (for sharing over
    WhatsApp) -- reuses one already issued for this MRN if it's still valid,
    same convention as the Purchase Order share link."""
    if not MrnData.objects.filter(div=div, mrn_no=mrn_no).exists():
        return None
    return MrnShareLink.get_or_create_for(div, mrn_no).token


def get_mrn_by_share_token(token):
    """The (div, mrn_no) a public share link's token points to, or (None, None)
    if the token is unknown, expired, or revoked."""
    link = MrnShareLink.objects.filter(token=token).first()
    if not link or not link.is_valid():
        return None, None
    return link.div, link.mrn_no


def get_mrn(div, mrn_no):
    """One MRN's header + its line items (from imaster -- see services.py's own
    module docstring and ItemMasterTransaction's docstring)."""
    header = MrnData.objects.filter(div=div, mrn_no=mrn_no).first()
    if not header:
        return None
    party = Party.objects.filter(party_code=header.party_code).first()
    items = _mrn_items(div, mrn_no)
    part_names = dict(Part.objects.filter(
        part_number__in={r["item_code"] for r in items if r["item_code"]}
    ).values_list("part_number", "description_1"))
    total_discount = sum((r["discount_amount"] or 0) for r in items)
    # The print layout shows one P.O. No in its header summary (not per line) --
    # the common case is every item on one MRN coming from the same PO; shown
    # only when that's actually true here, left blank if the items span more than one.
    distinct_po_nos = {_clean(r["po_no"]) for r in items if _clean(r["po_no"])}
    header_po_no = next(iter(distinct_po_nos)) if len(distinct_po_nos) == 1 else ""
    return {
        "div": (header.div or "").strip(),
        "mrn_no": header.mrn_no,
        "mrn_date": header.mrn_date.isoformat() if header.mrn_date else "",
        "party_code": (header.party_code or "").strip(),
        "party_name": _clean(party.name) if party else "",
        "party_address_1": _clean(party.address_1) if party else "",
        "party_address_2": _clean(party.address_2) if party else "",
        "party_phone": _clean(party.phone_1) or _clean(party.mobile_1) if party else "",
        "party_gst_no": _clean(party.gst_no) if party else "",
        "city": _clean(party.city) if party else "",
        "po_no": header_po_no,
        "bill_no": _clean(header.bill_no),
        "bill_date": header.bill_date.isoformat() if header.bill_date else "",
        "challan_no": _clean(header.challan_no),
        "challan_date": header.challan_date.isoformat() if header.challan_date else "",
        "transport": _clean(header.transport),
        "gr_no": _clean(header.gr_no),
        "check_po": _clean(header.check_po) or "Y",
        "gr_date": header.gr_date.isoformat() if header.gr_date else "",
        "remarks": _clean(header.remarks),
        "amount": _money(header.amount),
        "discount_amount": _money(total_discount),
        "gst_amount": _money(header.gst_amount),
        "other_charge_1": _money(header.other_charge_1),
        "other_charge_2": _money(header.other_charge_2),
        "net_amount": _money(header.net_amount),
        "ac_transferred": _clean(header.ac_transferred) or "N",
        "mrn_closed": _clean(header.mrn_closed) or "N",
        "items": [
            {
                "part_code": _clean(r["item_code"]),
                "part_name": _clean(part_names.get(r["item_code"])),
                "po_div": _clean(r["po_div"]),
                "po_no": _clean(r["po_no"]),
                "po_date": r["po_date"].isoformat() if r["po_date"] else "",
                "po_qty": _qty(r["po_qty"]),
                "size": _clean(r["size"]),
                "unit": _clean(r["unit"]),
                # No separate "Qty Received" column was found on imaster (see
                # ItemMasterTransaction's docstring) -- shown here as accepted
                # + rejected, which is what it actually means.
                "invoice_qty": _qty(r["quantity"]),
                "qty_received": _qty((r["quantity"] or 0) + (r["qty_rejected"] or 0)),
                "qty_accepted": _qty(r["quantity"]),
                "qty_rejected": _qty(r["qty_rejected"]),
                "rate": f"{(r['rate'] or 0):.4f}",
                "discount_percent": f"{(r['discount_percent'] or 0):.2f}",
                "discount_amount": _money(r["discount_amount"]),
                "gst_percent": f"{(r['gst_percent'] or 0):.2f}",
                "amount": _money(r["amount"]),
            }
            for r in items
        ],
    }


# --- Pending PO lookup (for "Check PO Y/N") ------------------------------------------

def pending_po_for(party_code, part_code):
    """The PO line this party/part is still pending against, if any -- checked
    against the live "order" table (PurchaseOrderItem). The legacy VFP code
    checked a table called "torder" instead; that table turned out to be a
    stale, unmaintained mirror (confirmed by comparing row counts and recent
    PO numbers against "order" -- new POs created through this app never show
    up in "torder"), so this intentionally does NOT use it."""
    rows = PurchaseOrderItem.objects.filter(party_code=party_code, part_code=part_code).values(
        "div", "po_no", "order_date", "po_qty", "quantity", "received_qty", "rate", "size", "discount_percent",
    )
    for r in rows:
        # MRN receives against the P.O. Qty (po_qty / "stock"), not the separate Qty
        # (stk_qty) -- the two can legitimately differ on a PO line (e.g. P.O. Qty 10,
        # Qty 100), and the vendor invoices the P.O. Qty at the PO rate. Old lines saved
        # without a P.O. Qty fall back to Qty so they still show as pending.
        ordered = r["po_qty"] if r["po_qty"] else (r["quantity"] or Decimal("0"))
        pending = ordered - (r["received_qty"] or Decimal("0"))
        if pending > 0:
            return {
                "div": (r["div"] or "").strip(),
                "po_no": r["po_no"],
                "po_date": r["order_date"].isoformat() if r["order_date"] else "",
                "pending_qty": _qty(pending),
                "rate": f"{(r['rate'] or 0):.4f}",
                "size": _clean(r["size"]),
                "discount_percent": f"{(r['discount_percent'] or 0):.2f}",
            }
    return None


# --- Save / Close / Delete ------------------------------------------------------------

def _validate_items(items):
    if not isinstance(items, list) or not items:
        raise MrnError("Add at least one item.", {"": "Add at least one item."})
    codes = {(row or {}).get("part_code", "").strip().upper() for row in items}
    known = set(Part.objects.filter(part_number__in=codes).values_list("part_number", flat=True))
    cleaned = []
    for row in items:
        code = (row.get("part_code") or "").strip().upper()
        if code not in known:
            raise MrnError("Some items are not valid.", {"": f"Unknown part: {code}"})
        qty_accepted = Decimal(str(row.get("qty_accepted") or 0))
        rate = Decimal(str(row.get("rate") or 0))
        discount_percent = Decimal(str(row.get("discount_percent") or 0))
        gross = qty_accepted * rate
        discount_amount = (gross * discount_percent / Decimal("100")).quantize(Decimal("0.01"))
        amount = (gross - discount_amount).quantize(Decimal("0.01"))
        cleaned.append({
            "item_code": code,
            "po_div": (row.get("po_div") or "").strip(),
            "po_no": (row.get("po_no") or "").strip(),
            "po_date": row.get("po_date") or None,
            "size": (row.get("size") or "")[:12],
            "unit": (row.get("unit") or "")[:3],
            "quantity": qty_accepted,  # "Qty Acpt" -- see ItemMasterTransaction's docstring
            "qty_rejected": Decimal(str(row.get("qty_rejected") or 0)),
            "rate": rate,
            "discount_percent": discount_percent,
            "discount_amount": discount_amount,
            "gst_percent": Decimal(str(row.get("gst_percent") or 0)),
            "amount": amount,
        })
    return cleaned


def _apply_po_received(items, sign):
    """Adds (sign=+1) or reverses (sign=-1) each item's accepted quantity
    against the PO line it was received against. Matched by (div, po_no,
    part_code) -- the "order" table has no reliable per-row key (see
    PurchaseOrderItem's own docstring), so a PO with the same part listed
    twice would have both rows receive the same update; the Purchase Order
    form itself already refuses to add the same part twice to one order, so
    this only affects old legacy data that predates that rule."""
    for item in items:
        if not item["po_no"] or not item["quantity"]:
            continue
        # Coalesce(received_qty, 0) -- a freshly-created PO line's received_qty is
        # NULL (never initialised on Confirm; see purchase_orders.services.save()),
        # and plain F("received_qty") + x against a NULL column evaluates to NULL
        # in SQL (NULL + anything = NULL), so the UPDATE silently kept writing NULL
        # back instead of accumulating -- the very first MRN received against a PO
        # line never actually reduced its pending quantity, and deleting that MRN
        # then had nothing real to undo either. Coalescing to 0 first fixes both.
        PurchaseOrderItem.objects.filter(
            div=item["po_div"] or DEFAULT_DIV, po_no=item["po_no"], part_code=item["item_code"],
        ).update(
            received_qty=Coalesce(F("received_qty"), Value(Decimal("0")), output_field=DecimalField())
            + sign * item["quantity"]
        )


def save_mrn(div, party_code, mrn_date, items, key=None, bill_no="", bill_date=None,
             challan_no="", challan_date=None, transport="", gr_no="", gr_date=None,
             remarks="", check_po="Y", other_charge_1=0, other_charge_2=0, username=""):
    """ADD (key is None) or MODIFY (key given) one MRN + its items, in one
    transaction. MODIFY reverses the old items' effect on PO received
    quantities before applying the new items' effect, so re-saving an MRN
    never double-counts stock received."""
    _require_writes()
    div = (div or DEFAULT_DIV).strip().upper() or DEFAULT_DIV
    party_code = (party_code or "").strip().upper()
    errors = {}
    if not party_code:
        errors["party_code"] = "Select a party."
    elif not Party.objects.filter(party_code=party_code).exists():
        errors["party_code"] = "Select a party from the Party Master."
    if not mrn_date:
        errors["mrn_date"] = "MRN date is required."
    if errors:
        raise MrnError("Fix the highlighted fields.", errors)

    cleaned = _validate_items(items)
    total_amount = sum((i["amount"] for i in cleaned), Decimal("0"))
    total_gst = sum((i["amount"] * i["gst_percent"] / Decimal("100") for i in cleaned), Decimal("0")).quantize(Decimal("0.01"))

    with transaction.atomic(using=MrnData.objects.db):
        if key:
            old_div, old_mrn_no = key
            header = MrnData.objects.select_for_update().filter(div=old_div, mrn_no=old_mrn_no).first()
            if not header:
                raise MrnError("This MRN no longer exists.")
            if _clean(header.mrn_closed) == "Y":
                raise MrnError("MRN is Closed, Unable to Modify.")
            if _clean(header.ac_transferred) == "Y":
                raise MrnError("A/C TRANSFERED, Unable to Modify.")
            old_items = list(ItemMasterTransaction.objects.filter(mrn_no=old_mrn_no).values(
                "po_div", "po_no", "item_code", "quantity",
            ))
            _apply_po_received(old_items, sign=-1)
            ItemMasterTransaction.objects.filter(mrn_no=old_mrn_no, mrn_flag="Y").delete()
            mrn_no = old_mrn_no
        else:
            mrn_no = _allocate_mrn_no()
            header = MrnData(div=div, mrn_no=mrn_no)

        header.party_code = party_code
        header.mrn_date = mrn_date
        header.bill_no = bill_no[:8]
        header.bill_date = bill_date
        header.challan_no = challan_no[:8]
        header.challan_date = challan_date
        header.transport = transport[:20]
        header.gr_no = gr_no[:15]
        header.gr_date = gr_date
        header.remarks = remarks[:40]
        header.check_po = (check_po or "Y")[:1].upper()
        oc1 = Decimal(str(other_charge_1 or 0))
        oc2 = Decimal(str(other_charge_2 or 0))
        header.other_charge_1 = oc1
        header.other_charge_2 = oc2
        header.amount = total_amount
        header.gst_amount = total_gst
        header.net_amount = total_amount + total_gst + oc1 + oc2
        header.mrn_closed = _clean(header.mrn_closed) or "N"
        header.ac_transferred = _clean(header.ac_transferred) or "N"
        header.uname = username[:10]
        header.save()
        _audit(div, mrn_no, "MODIFY" if key else "ADD", username)

        ItemMasterTransaction.objects.bulk_create([
            ItemMasterTransaction(div=div, mrn_no=mrn_no, bill_no=bill_no[:9], bill_date=bill_date,
                                   mrn_date=mrn_date, mrn_flag="Y", po_qty=item["quantity"],
                                   party_code=party_code, uname=username[:10], **item)
            for item in cleaned
        ])
        _apply_po_received(cleaned, sign=+1)

    return {"div": div, "mrn_no": mrn_no}


def close_mrn(div, mrn_no, username=""):
    """CLOSE MRN: old VFP -- IF mrn_cl='Y' THEN "MRN Already Closed" ELSE confirm
    and set mrn_cl='Y'. Distinct from ac_transferred -- a closed MRN can still
    be un-transferred, and this never touches that flag."""
    _require_writes()
    with transaction.atomic(using=MrnData.objects.db):
        header = MrnData.objects.select_for_update().filter(div=div, mrn_no=mrn_no).first()
        if not header:
            raise MrnError("This MRN no longer exists.")
        if _clean(header.mrn_closed) == "Y":
            raise MrnError("MRN Already Closed.")
        header.mrn_closed = "Y"
        header.save(update_fields=["mrn_closed"])
        _audit(div, mrn_no, "CLOSE", username)


def delete_mrn(div, mrn_no, username=""):
    """DELETE: blocked once A/C TRANSFERED (ac_tf='Y'), same as MODIFY. Reverses
    this MRN's items' effect on PO received quantities, then removes the items
    and the header. The old VFP code also rolled the sp_mrn_no counter back by
    one, but only when the MRN being deleted was the latest number issued;
    this preserves that same guard, so deleting an older MRN never reassigns
    a number that's already been used."""
    _require_writes()
    with transaction.atomic(using=MrnData.objects.db):
        header = MrnData.objects.select_for_update().filter(div=div, mrn_no=mrn_no).first()
        if not header:
            raise MrnError("This MRN no longer exists.")
        if _clean(header.mrn_closed) == "Y":
            raise MrnError("MRN is Closed, Unable to Delete.")
        if _clean(header.ac_transferred) == "Y":
            raise MrnError("A/C TRANSFERED, Unable to Delete.")
        items = list(ItemMasterTransaction.objects.filter(mrn_no=mrn_no).values(
            "po_div", "po_no", "item_code", "quantity",
        ))
        _apply_po_received(items, sign=-1)
        ItemMasterTransaction.objects.filter(mrn_no=mrn_no, mrn_flag="Y").delete()
        header.delete()
        _audit(div, mrn_no, "DELETE", username)
        current = _first_value(InvNo.objects.select_for_update().values_list("next_mrn_no", flat=True))
        if current is not None and str(int(current)) == str(mrn_no):
            InvNo.objects.update(next_mrn_no=int(mrn_no) - 1)


# --- Pending MRN report -------------------------------------------------------------
#
# Old VFP form: "PENDING MRN". An MRN is pending when EMPTY(mrn_cl) -- the old
# software's "blank" convention. This project's live data instead always sets
# mrn_cl to a real 'Y' or 'N' (confirmed against real rows: never actually
# blank), matching the MRN list screen's own "mrn_closed or 'N'" display
# convention -- so "pending" here means mrn_cl != 'Y', not literally blank.
#   mrn_cl != 'Y'  AND  mrn_dt >= start_date  AND  mrn_dt <= end_date
# (never checks ac_tf/A-C-transferred -- only mrn_cl, unlike the MRN list screen's
# own "closed" filter which is a user choice, not baked into this report).

def pending_mrns(start_date, end_date):
    """[{div, mrn_date, mrn_no, party_name, party_city}, ...] -- MRNs not yet
    closed, in the given date range, same row order as the VFP SCAN (MRN table
    order, not re-sorted)."""
    rows = list(
        MrnData.objects.filter(mrn_date__gte=start_date, mrn_date__lte=end_date)
        .exclude(mrn_closed="Y")
        .values("div", "mrn_no", "mrn_date", "party_code")
    )
    names, cities, _mobiles = _party_names_and_cities(r["party_code"] for r in rows)
    result = []
    for r in rows:
        party = (r["party_code"] or "").strip()
        result.append({
            "div": (r["div"] or "").strip(),
            "mrn_no": r["mrn_no"],
            "mrn_date": r["mrn_date"].isoformat() if r["mrn_date"] else "",
            "party_name": _clean(names.get(party)),
            "party_city": _clean(cities.get(party)),
        })
    return result


# --- Current Stock report ---------------------------------------------------------------
#
# Old VFP report: "CURRENT STOCK". For every part, balance = opening stock (op_stk)
# + movements before the start date, then movements in the range (legacy scan
# rules, each on imaster):
#   P  MRN lines (mrn_no set)          +po_qty  on m_dat
#   R  receipts (bill_no, stts R)      +qty     on date
#   I  issues  (bill_no, stts I)       -qty     on date
#   S  sale bills (bill_no, stts S)    -qty     on date
#   A  debit notes (gdb_no set)        -qty     on date (same rule as apps.mrn.part_ledger._movements)
# NOT YET MAPPED here (left out, so the balance is incomplete for parts using them):
#   T  credit notes (i_master.gcr_no), B  job work (job_no/jo_no/jb_no -- no column on
#   ItemMasterTransaction yet).
# Parts whose balance is zero are not listed (old VFP: IF mbalstk # 0).

_SIGN = {"P": 1, "R": 1, "I": -1, "S": -1, "A": -1}


def _movements():
    from apps.purchase_orders.models import ItemMasterTransaction as IMT
    rows = []
    for r in IMT.objects.filter(mrn_no__isnull=False).exclude(mrn_no="").values("item_code", "po_qty", "mrn_date"):
        rows.append(("P", r["item_code"], r["po_qty"], r["mrn_date"]))
    for r in IMT.objects.exclude(bill_no__isnull=True).exclude(bill_no="").filter(status__in=["R", "I", "S"])             .values("item_code", "status", "quantity", "bill_date"):
        rows.append((r["status"], r["item_code"], r["quantity"], r["bill_date"]))
    for r in IMT.objects.exclude(debit_note_no__isnull=True).exclude(debit_note_no="")             .values("item_code", "quantity", "bill_date"):
        rows.append(("A", r["item_code"], r["quantity"], r["bill_date"]))
    return rows


def current_stock_report(start_date, end_date):
    from apps.parts.models import Part

    movements = _movements()
    pre, period = {}, {}
    for kind, code, qty, dt in movements:
        if not code or dt is None:
            continue
        code = code.strip()
        amount = (qty or Decimal("0")) * _SIGN[kind]
        if dt < start_date:
            pre[code] = pre.get(code, Decimal("0")) + amount
        elif dt <= end_date:
            period[code] = period.get(code, Decimal("0")) + amount

    result = []
    for part in Part.objects.order_by("part_number"):
        code = (part.part_number or "").strip()
        opening = part.opening_stock or Decimal("0")
        balance = opening + pre.get(code, Decimal("0")) + period.get(code, Decimal("0"))
        if balance == 0:
            continue
        result.append({
            "item_code": code,
            "item_name": _clean(part.description_1),
            "stock": f"{balance:.2f}",
        })
    for sno, row in enumerate(result, start=1):
        row["sno"] = sno
    return result


# --- Stock Statement -------------------------------------------------------------------
#
# Old VFP report: "STOCK STATEMENT" (grn/stkstmt). Per part:
#   opening  = op_stk + receipts before start - issues before start
#   period   = receipts (and issues) in [start, end]
#   balance  = opening + receipts - issues
# Movement rules, as the legacy scan has them (imaster):
#   issues   stts in (S, I) or debit notes (stts 'A'), with mrn blank  -- by date
#   receipts stts 'R' with mrn blank                                   -- by date
#   MRN      rows with mrn_no set (stts is blank on these, not 'P')    -- received, by m_dat
# Confirmed against real data (item ABM_99): an MRN row's own stts column is
# NULL, never 'P' -- filtering on status='P' (as this used to) matches nothing,
# so MRN receipts were silently dropped; and 'A' (debit note, reduces stock,
# same direction apps.mrn.part_ledger._movements already treats it) had been
# bucketed as a receipt instead of an issue, double-counting it the wrong way.
# NOT YET MAPPED: credit notes (stts T, held in i_master) and job work (job_no/jo_no/jb_no),
# which the legacy statement counts; parts using them won't reconcile.
# Only parts with a non-zero opening, receipt or issue are listed (old VFP: fl=1).

def _statement_movements():
    from apps.purchase_orders.models import ItemMasterTransaction as IMT
    no_mrn = models.Q(mrn_no__isnull=True) | models.Q(mrn_no="")
    issues = IMT.objects.filter(status__in=["S", "I", "A"]).filter(no_mrn) \
        .exclude(item_code__isnull=True).values("item_code", "quantity", "bill_date")
    receipts = IMT.objects.filter(status="R").filter(no_mrn) \
        .exclude(item_code__isnull=True).values("item_code", "quantity", "bill_date")
    mrn = IMT.objects.exclude(mrn_no__isnull=True).exclude(mrn_no="") \
        .exclude(item_code__isnull=True).values("item_code", "quantity", "mrn_date")
    return issues, receipts, mrn


def stock_statement(start_date, end_date):
    from apps.parts.models import Part

    issues, receipts, mrn = _statement_movements()
    pre_rec, pre_iss, per_rec, per_iss = {}, {}, {}, {}

    def add(bucket, code, qty):
        bucket[code] = bucket.get(code, Decimal("0")) + (qty or Decimal("0"))

    for r in issues:
        code = r["item_code"].strip()
        if r["bill_date"] is None:
            continue
        if r["bill_date"] < start_date:
            add(pre_iss, code, r["quantity"])
        elif r["bill_date"] <= end_date:
            add(per_iss, code, r["quantity"])
    for r in receipts:
        code = r["item_code"].strip()
        if r["bill_date"] is None:
            continue
        if r["bill_date"] < start_date:
            add(pre_rec, code, r["quantity"])
        elif r["bill_date"] <= end_date:
            add(per_rec, code, r["quantity"])
    for r in mrn:
        code = r["item_code"].strip()
        if r["mrn_date"] is None:
            continue
        if r["mrn_date"] < start_date:
            add(pre_rec, code, r["quantity"])
        elif r["mrn_date"] <= end_date:
            add(per_rec, code, r["quantity"])

    result = []
    for part in Part.objects.order_by("part_number"):
        code = (part.part_number or "").strip()
        opening = (part.opening_stock or Decimal("0")) + pre_rec.get(code, Decimal("0")) - pre_iss.get(code, Decimal("0"))
        rec = per_rec.get(code, Decimal("0"))
        iss = per_iss.get(code, Decimal("0"))
        if opening == 0 and rec == 0 and iss == 0:
            continue
        rate = part.purchase_rate or Decimal("0")
        balance = opening + rec - iss
        weight = (part.weight_by_100 or Decimal("0")) / 100 * balance
        result.append({
            "item_code": code,
            "item_name": _clean(part.description_1),
            "unit": _clean(part.unit),
            "grade": _clean(part.grade),
            "rol": f"{(part.reorder_qty or 0):.2f}",
            "material": _clean(part.material),
            "wt100": f"{(part.weight_by_100 or 0):.3f}",
            "opening": f"{opening:.3f}",
            "received": f"{rec:.3f}",
            "issued": f"{iss:.3f}",
            "rate": f"{rate:.2f}",
            "balance": f"{balance:.3f}",
            "balance_value": f"{balance * rate:.2f}",
            "weight": f"{weight:.3f}",
        })
    for sno, row in enumerate(result, start=1):
        row["sno"] = sno
    return result


# --- Raw Material Stock Ledger (value-wise) ---------------------------------------------
#
# Old VFP report: "RAW MATERIAL STOCK LEDGER". Same movement rules as the Stock
# Statement above (issues S/I, receipts R/A and MRN lines P), applied to every part
# of the chosen grade -- ALL = every grade, SINGLE = only the typed grade. Every part
# is listed, including zero balances (the legacy ledger has no non-zero filter).
# Value = balance x purchase rate; weight = wt/100 x balance.

def stock_ledger(start_date, end_date, grade=None):
    from apps.parts.models import Part

    issues, receipts, mrn = _statement_movements()
    pre_rec, pre_iss, per_rec, per_iss = {}, {}, {}, {}

    def add(bucket, code, qty):
        bucket[code] = bucket.get(code, Decimal("0")) + (qty or Decimal("0"))

    for r in issues:
        code = r["item_code"].strip()
        if r["bill_date"] is None:
            continue
        if r["bill_date"] < start_date:
            add(pre_iss, code, r["quantity"])
        elif r["bill_date"] <= end_date:
            add(per_iss, code, r["quantity"])
    for r in receipts:
        code = r["item_code"].strip()
        if r["bill_date"] is None:
            continue
        if r["bill_date"] < start_date:
            add(pre_rec, code, r["quantity"])
        elif r["bill_date"] <= end_date:
            add(per_rec, code, r["quantity"])
    for r in mrn:
        code = r["item_code"].strip()
        if r["mrn_date"] is None:
            continue
        if r["mrn_date"] < start_date:
            add(pre_rec, code, r["quantity"])
        elif r["mrn_date"] <= end_date:
            add(per_rec, code, r["quantity"])

    parts = Part.objects.order_by("part_number")
    if grade is not None:
        parts = parts.filter(grade=grade.strip())
    result = []
    for part in parts:
        code = (part.part_number or "").strip()
        balance = ((part.opening_stock or Decimal("0"))
                   + pre_rec.get(code, Decimal("0")) - pre_iss.get(code, Decimal("0"))
                   + per_rec.get(code, Decimal("0")) - per_iss.get(code, Decimal("0")))
        rate = part.purchase_rate or Decimal("0")
        result.append({
            "item_code": code,
            "item_name": _clean(part.description_1),
            "balance": f"{balance:.3f}",
            "value": f"{balance * rate:.2f}",
            "weight": f"{(part.weight_by_100 or Decimal('0')) / 100 * balance:.3f}",
        })
    return result


# --- Item-wise Month-wise Sale (qty) -------------------------------------------------
#
# Old VFP report: "ITEM-WISE/MONTHWISE SALE REPORT (QTY WISE)". Sales quantity per item
# per month of the financial year (April to March), from imaster rows with stts='S' and
# date on/after the financial-year start (old VFP: date>=pfyfrom, no upper bound).
# Average monthly sale = total / 12 (the report's own RE.ORD basis). Value = average x
# the part's invoice rate (inv_rt). The legacy "update RE.ORD QTY" option is NOT carried
# over here -- the report only displays.

FY_MONTH_ORDER = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]


def item_monthwise_sale(fy_start):
    from apps.parts.models import Part
    from apps.purchase_orders.models import ItemMasterTransaction as IMT

    sales = IMT.objects.filter(status="S", bill_date__gte=fy_start).exclude(item_code__isnull=True) \
        .values("item_code", "bill_date", "quantity")
    per_item = {}
    for r in sales:
        if r["bill_date"] is None:
            continue
        code = r["item_code"].strip()
        slots = per_item.setdefault(code, [Decimal("0")] * 12)
        slots[FY_MONTH_ORDER.index(r["bill_date"].month)] += (r["quantity"] or Decimal("0"))

    result = []
    invoice_rates = dict(Item.objects.values_list("item_code", "invoice_rate"))
    for part in Part.objects.order_by("part_number"):
        code = (part.part_number or "").strip()
        if code not in per_item:
            continue
        months = per_item[code]
        total = sum(months, Decimal("0"))
        average = total / Decimal("12")
        rate = Decimal(str(invoice_rates.get(code) or 0))
        result.append({
            "item_code": code,
            "item_name": _clean(part.description_1),
            "unit": _clean(part.unit),
            "rop": f"{(part.reorder_qty or Decimal('0')):.2f}",
            "months": [f"{m:.2f}" for m in months],
            "total": f"{total:.2f}",
            "total_value": f"{(total * rate):.2f}",
            "value": f"{(average * rate):.2f}",
            "average": f"{average:.2f}",
        })
    return result


# --- Critical Shortage (stock statement for shortages) ----------------------------------
#
# Old VFP report: "STOCK STATE..." (critical shortage). Per part (ayn <> 'N'):
#   balance      = opening + receipts - issues (same rules as the Stock Statement)
#   cur-year use = issues in [start, end] / days in range x current-year days
#   requirement  = max(cur-year use, planning stock) when cur-year use > last-year days,
#                  otherwise max(last-year days, planning stock)  (legacy comparison)
#   pending      = open PO quantity (ordered - received); x 100 / wt if conv = 'Y'
# A part is listed when it has no pending order and balance < requirement; the
# shortage is requirement - balance. Last-year average = reorder qty / 30 x last-year days.
# NOT YET MAPPED: job-work consumption (stts X/Y) -- counted as zero here.

def critical_shortage(start_date, end_date, last_days, cur_days):
    from apps.parts.models import Part
    from apps.purchase_orders.models import PurchaseOrderItem

    issues, receipts, mrn = _statement_movements()
    pre_rec, pre_iss, per_rec, per_iss = {}, {}, {}, {}

    def add(bucket, code, qty):
        bucket[code] = bucket.get(code, Decimal("0")) + (qty or Decimal("0"))

    for r in issues:
        code = r["item_code"].strip()
        if r["bill_date"] is None:
            continue
        if r["bill_date"] < start_date:
            add(pre_iss, code, r["quantity"])
        elif r["bill_date"] <= end_date:
            add(per_iss, code, r["quantity"])
    for r in receipts:
        code = r["item_code"].strip()
        if r["bill_date"] is None:
            continue
        if r["bill_date"] < start_date:
            add(pre_rec, code, r["quantity"])
        elif r["bill_date"] <= end_date:
            add(per_rec, code, r["quantity"])
    for r in mrn:
        code = r["item_code"].strip()
        if r["mrn_date"] is None:
            continue
        if r["mrn_date"] < start_date:
            add(pre_rec, code, r["quantity"])
        elif r["mrn_date"] <= end_date:
            add(per_rec, code, r["quantity"])

    pending_by_part = {}
    for r in PurchaseOrderItem.objects.exclude(part_code__isnull=True).values("part_code", "quantity", "received_qty"):
        open_qty = (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0"))
        if open_qty > 0:
            code = r["part_code"].strip()
            pending_by_part[code] = pending_by_part.get(code, Decimal("0")) + open_qty

    span_days = Decimal((end_date - start_date).days or 1)
    parts = Part.objects.exclude(active_flag="N").order_by("part_number")
    supplier_codes = set()
    part_list = list(parts)
    for part in part_list:
        for c in (part.supplier_1, part.supplier_2, part.supplier_3, part.supplier_4):
            if c:
                supplier_codes.add(c.strip())
    from apps.parties.models import Party
    party_names = dict(Party.objects.filter(party_code__in=supplier_codes).values_list("party_code", "name"))

    result = []
    for part in part_list:
        code = (part.part_number or "").strip()
        balance = ((part.opening_stock or Decimal("0"))
                   + pre_rec.get(code, Decimal("0")) - pre_iss.get(code, Decimal("0"))
                   + per_rec.get(code, Decimal("0")) - per_iss.get(code, Decimal("0")))
        issued = per_iss.get(code, Decimal("0"))
        cur_use = issued / span_days * Decimal(cur_days)
        planning = part.planning_stock or Decimal("0")
        last_use = Decimal(last_days)
        if cur_use > last_use:
            requirement = max(cur_use, planning)
        else:
            requirement = max(last_use, planning)

        pending = pending_by_part.get(code, Decimal("0"))
        if (part.conversion_flag or "").strip() == "Y" and part.weight_by_100:
            pending = (Decimal("100") / part.weight_by_100) * pending
        if pending > 0:
            continue

        if balance > requirement:
            shortage, excess = Decimal("0"), balance - requirement
        else:
            shortage, excess = requirement - balance, Decimal("0")
        if shortage <= 0:
            continue

        rate = part.purchase_rate or Decimal("0")
        last_year_avg = (part.reorder_qty or Decimal("0")) / Decimal("30") * last_days
        suppliers = [_clean(party_names.get((c or "").strip())) if c else "" for c in
                     (part.supplier_1, part.supplier_2, part.supplier_3, part.supplier_4)]
        result.append({
            "item_code": code,
            "item_name": _clean(part.description_1),
            "unit": _clean(part.unit),
            "balance": f"{balance:.3f}",
            "value": f"{balance * rate:.2f}",
            "cur_use": f"{cur_use:.3f}",
            "last_use": f"{last_year_avg:.3f}",
            "planning": f"{planning:.3f}",
            "shortage": f"{shortage:.3f}",
            "excess": f"{excess:.3f}",
            "suppliers": suppliers,
        })
    for sno, row in enumerate(result, start=1):
        row["sno"] = sno
    return result


# --- Crisis Shortage (summary) ---------------------------------------------------------
#
# Old VFP report: "CRISIS SHORTAGE". Same balance and movement rules as the Critical
# Shortage above, with a user-chosen consumption window (days) and a category:
#   ALL        s_cod <> 'Y'
#   ROUTINE    routine = 'R' and s_cod <> 'Y' and ws <> 'Y'
#   SUB ASSY   routine = 'S' and s_cod = 'Y'
#   WORKSHOP   routine = ' ' and ws = 'Y'
# Annual rates are scaled to 30 days (legacy), and a part is listed when the closing
# balance falls below the larger of its window consumption and its reorder level.
# Each listed part shows its open purchase orders (vendor, PO no, pending qty, despatch).
# NOT YET MAPPED: the job-work sections (ws_job / new_job) that the legacy summary adds
# under each part -- those lines are not shown here.

def crisis_shortage(start_date, end_date, days, category):
    from apps.parts.models import Part
    from apps.parties.models import Party
    from apps.purchase_orders.models import PurchaseOrderItem

    issues, receipts, mrn = _statement_movements()
    pre_rec, pre_iss, per_rec, per_iss = {}, {}, {}, {}

    def add(bucket, code, qty):
        bucket[code] = bucket.get(code, Decimal("0")) + (qty or Decimal("0"))

    for r in issues:
        code = r["item_code"].strip()
        if r["bill_date"] is None:
            continue
        if r["bill_date"] < start_date:
            add(pre_iss, code, r["quantity"])
        elif r["bill_date"] <= end_date:
            add(per_iss, code, r["quantity"])
    for r in receipts:
        code = r["item_code"].strip()
        if r["bill_date"] is None:
            continue
        if r["bill_date"] < start_date:
            add(pre_rec, code, r["quantity"])
        elif r["bill_date"] <= end_date:
            add(per_rec, code, r["quantity"])
    for r in mrn:
        code = r["item_code"].strip()
        if r["mrn_date"] is None:
            continue
        if r["mrn_date"] < start_date:
            add(pre_rec, code, r["quantity"])
        elif r["mrn_date"] <= end_date:
            add(per_rec, code, r["quantity"])

    open_pos = {}
    for r in PurchaseOrderItem.objects.exclude(part_code__isnull=True).exclude(adjusted="Y") \
            .values("part_code", "po_no", "party_code", "quantity", "received_qty", "despatch_date"):
        open_qty = (r["quantity"] or Decimal("0")) - (r["received_qty"] or Decimal("0"))
        if open_qty > 0:
            open_pos.setdefault(r["part_code"].strip(), []).append({
                "po_no": _clean(r["po_no"]), "party_code": _clean(r["party_code"]),
                "pending": open_qty, "despatch": r["despatch_date"],
            })

    parts = Part.objects.exclude(active_flag="N").order_by("part_number")
    if category == "all":
        parts = parts.exclude(sub_assembly="Y")
    elif category == "routine":
        parts = parts.filter(routine_flag="R").exclude(sub_assembly="Y").exclude(workshop_flag="Y")
    elif category == "subassembly":
        parts = parts.filter(routine_flag="S", sub_assembly="Y")
    elif category == "workshop":
        parts = parts.filter(workshop_flag="Y").exclude(routine_flag__in=["R", "S"])
    part_list = list(parts)

    party_codes = {p["party_code"] for lst in open_pos.values() for p in lst if p["party_code"]}
    party_names = dict(Party.objects.filter(party_code__in=party_codes).values_list("party_code", "name"))

    span_days = Decimal((end_date - start_date).days or 1)
    window = Decimal(days)
    result = []
    for part in part_list:
        code = (part.part_number or "").strip()
        balance = ((part.opening_stock or Decimal("0"))
                   + pre_rec.get(code, Decimal("0")) - pre_iss.get(code, Decimal("0"))
                   + per_rec.get(code, Decimal("0")) - per_iss.get(code, Decimal("0")))
        issued = per_iss.get(code, Decimal("0"))
        msaleavg = issued / span_days * Decimal(30)
        rop = part.reorder_qty or Decimal("0")
        dummy = part.planning_stock or Decimal("0")
        if msaleavg > rop:
            mchk = max(msaleavg, dummy)
            mshort = max(msaleavg - balance, Decimal("0"))
        else:
            mchk = max(rop, dummy)
            mshort = max(rop - balance, Decimal("0"))
        if mshort <= 0:
            continue
        mmax = max(msaleavg / 30 * window, rop / 30 * window)
        if balance - mmax >= 0:
            continue
        shortage = abs(balance - mmax)
        pos = open_pos.get(code, [])
        base = {
            "item_code": code,
            "item_name": _clean(part.description_1),
            "unit": _clean(part.unit),
            "cur_avg": f"{msaleavg / 30 * window:.3f}",
            "last_avg": f"{rop / 30 * window:.3f}",
            "balance": f"{balance:.3f}",
            "shortage": f"{shortage:.3f}",
        }
        if not pos:
            result.append({**base, "vendor": "", "po_no": "", "pending": "", "despatch": ""})
        for po in pos:
            result.append({
                **base,
                "vendor": _clean(party_names.get(po["party_code"])),
                "po_no": po["po_no"],
                "pending": f"{po['pending']:.3f}",
                "despatch": po["despatch"].isoformat() if po["despatch"] else "",
            })
    for sno, row in enumerate(result, start=1):
        row["sno"] = sno
    return result

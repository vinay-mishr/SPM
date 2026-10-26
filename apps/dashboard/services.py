"""Dashboard home: KPI counts, charts and summary tables, read from the legacy
SQL Server tables the rest of the ERP already queries (see apps.sale_order.services
for the same ord_mst/order1 raw-SQL pattern this module follows for sales orders).
"""
from collections import OrderedDict
from datetime import date
from decimal import Decimal

from django.db import connections
from django.utils import timezone

from apps.parts.models import Part

STATUS_OPEN = "Open"
STATUS_IN_PROGRESS = "In Progress"
STATUS_COMPLETED = "Completed"


def _d(value):
    return Decimal(str(value or 0))


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _rows(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _order_status(total_stock, total_issue):
    if total_issue <= 0:
        return STATUS_OPEN
    if total_issue < total_stock:
        return STATUS_IN_PROGRESS
    return STATUS_COMPLETED


def _order_lines_by_order():
    """{(div, order): {"date", "party_code", "amount", "stock", "issue"}} for live lines."""
    rows = _rows(
        "SELECT div, [order], date, p_code, stock, issue, brate, cdis "
        "FROM order1 WHERE COALESCE(adj, '') <> 'Y'"
    )
    orders = OrderedDict()
    for r in rows:
        key = (_clean(r["div"]) or "", _clean(r["order"]) or "")
        o = orders.get(key)
        if o is None:
            o = orders[key] = {
                "date": r["date"], "party_code": _clean(r["p_code"]) or "",
                "amount": Decimal("0"), "stock": Decimal("0"), "issue": Decimal("0"),
            }
        gross = _d(r["stock"]) * _d(r["brate"])
        o["amount"] += gross - gross * _d(r["cdis"]) / 100
        o["stock"] += _d(r["stock"])
        o["issue"] += _d(r["issue"])
    return orders


def sale_of_the_day():
    """Gross sales booked today from the shared ``bill`` header table
    (bill_type='G' machine invoices, 'P' spare-part invoices). Proforma and
    quotation screens never post here, so they're excluded by construction.
    Figures are gross invoice totals, not net of credit notes: the legacy
    credit-note tables (c_bill/g_master) have no confirmed link back into
    bill.n_amount, so there is nothing reliable to subtract. Also distinct
    from "collections" (money_receipt), which records payments, not sales."""
    today = timezone.localdate()
    rows = _rows(
        "SELECT bill_no, div, vou_no, bill_type, n_amount FROM bill WHERE bill_type IN ('G', 'P') AND b_date = %s",
        [today],
    )
    machine_sales = Decimal("0")
    spare_sales = Decimal("0")
    machine_invoices = set()
    spare_invoices = set()
    for r in rows:
        if (r["bill_type"] or "").strip() == "G":
            machine_sales += _d(r["n_amount"])
            machine_invoices.add(_clean(r["bill_no"]))
        else:
            spare_sales += _d(r["n_amount"])
            spare_invoices.add((_clean(r["bill_no"]), _clean(r["div"]), _clean(r["vou_no"])))

    machine_qty = _rows(
        "SELECT SUM(m.qty) AS qty FROM i_master m JOIN bill b ON b.bill_no = m.bill_no AND b.bill_type = m.bill_type "
        "WHERE m.bill_type = 'G' AND b.b_date = %s",
        [today],
    )
    spare_qty = _rows(
        "SELECT SUM(m.qty) AS qty FROM imaster m "
        "JOIN bill b ON b.bill_no = m.bill_no AND b.bill_type = m.bill_type AND b.div = m.div "
        "WHERE m.bill_type = 'P' AND COALESCE(m.stts, '') <> 'X' AND b.b_date = %s",
        [today],
    )
    return {
        "total_sales": machine_sales + spare_sales,
        "machine_sales": machine_sales,
        "spare_sales": spare_sales,
        "total_invoices": len(machine_invoices) + len(spare_invoices),
        "machine_qty": _d(machine_qty[0]["qty"]) if machine_qty else Decimal("0"),
        "spare_qty": _d(spare_qty[0]["qty"]) if spare_qty else Decimal("0"),
    }


def recent_sales_invoices(limit=8):
    """Most recent machine + spare-part invoices, merged, newest first, with a Type column."""
    custs = {r["ccode"].strip(): r["cname"] for r in _rows("SELECT ccode, cname FROM cust_mst") if r["ccode"]}
    machine = _rows(
        "SELECT TOP (%s) bill_no, b_date, p_code, n_amount FROM bill WHERE bill_type = 'G' ORDER BY b_date DESC, bill_no DESC",
        [int(limit)],
    )
    spare = _rows(
        "SELECT TOP (%s) bill_no, div, vou_no, b_date, p_code, n_amount FROM bill "
        "WHERE bill_type = 'P' ORDER BY b_date DESC, bill_no DESC",
        [int(limit)],
    )
    out = []
    for r in machine:
        out.append({
            "invoice_no": _clean(r["bill_no"]) or "",
            "date": r["b_date"],
            "party_name": custs.get(_clean(r["p_code"]) or "", "") or "",
            "amount": _d(r["n_amount"]),
            "type": "Machine",
        })
    for r in spare:
        out.append({
            "invoice_no": _clean(r["bill_no"]) or "",
            "date": r["b_date"],
            "party_name": custs.get(_clean(r["p_code"]) or "", "") or "",
            "amount": _d(r["n_amount"]),
            "type": "Spare Part",
        })
    out.sort(key=lambda r: r["date"] or date.min, reverse=True)
    return out[:limit]


def _add_months(year, month, offset):
    total = (year * 12 + (month - 1)) + offset
    return total // 12, total % 12 + 1


def orders_overview(months=6):
    """Order count per month for the last `months` months (current month included), oldest first."""
    today = timezone.localdate()
    start_year, start_month = _add_months(today.year, today.month, -(months - 1))
    start = date(start_year, start_month, 1)
    rows = _rows(
        "SELECT div, [order], ord_date FROM ord_mst WHERE ord_date >= %s ORDER BY ord_date",
        [start],
    )
    buckets = OrderedDict()
    for i in range(months):
        y, m = _add_months(start_year, start_month, i)
        buckets[(y, m)] = 0
    for r in rows:
        d = r["ord_date"]
        if not d:
            continue
        key = (d.year, d.month)
        if key in buckets:
            buckets[key] += 1
    labels = [date(y, m, 1).strftime("%b %Y") for (y, m) in buckets]
    return {"labels": labels, "values": list(buckets.values())}


def recent_sales_orders(limit=8):
    custs = {r["ccode"].strip(): r["cname"] for r in _rows("SELECT ccode, cname FROM cust_mst") if r["ccode"]}
    items = {r["i_code"].strip(): r["i_name"] for r in _rows("SELECT i_code, i_name FROM item") if r["i_code"]}
    rows = _rows(
        "SELECT TOP (%s) o.div, o.[order], o.ord_date, o.p_code, o.amount1 "
        "FROM ord_mst o ORDER BY o.ord_date DESC, o.[order] DESC",
        [int(limit)],
    )
    orders = _order_lines_by_order()
    first_items = {}
    for r in _rows("SELECT div, [order], i_code FROM order1 WHERE COALESCE(adj, '') <> 'Y'"):
        key = (_clean(r["div"]) or "", _clean(r["order"]) or "")
        first_items.setdefault(key, _clean(r["i_code"]) or "")

    out = []
    for r in rows:
        key = (_clean(r["div"]) or "", _clean(r["order"]) or "")
        o = orders.get(key)
        status = _order_status(o["stock"], o["issue"]) if o else STATUS_COMPLETED
        item_code = first_items.get(key, "")
        out.append({
            "order_no": _clean(r["order"]) or "",
            "date": r["ord_date"],
            "party_name": custs.get((_clean(r["p_code"]) or ""), "") or "",
            "item_name": items.get(item_code, "") or item_code,
            "amount": _d(r["amount1"]),
            "status": status,
        })
    return out


def low_stock_materials(limit=8):
    parts = (
        Part.objects.filter(reorder_qty__isnull=False, current_stock__isnull=False)
        .exclude(active_flag="N")
    )
    shortages = []
    for p in parts:
        reorder = _d(p.reorder_qty)
        current = _d(p.current_stock)
        if reorder > 0 and current <= reorder:
            shortages.append({
                "name": p.description_1 or p.part_number,
                "current_stock": current,
                "reorder_level": reorder,
                "critical": current <= reorder / 2,
            })
    shortages.sort(key=lambda s: (s["current_stock"] - s["reorder_level"]))
    return shortages[:limit]

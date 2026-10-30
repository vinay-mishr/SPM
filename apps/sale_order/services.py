"""Sale Order Entry (VFP SALE ORDER FORM): ord_mst header, order1 lines, item.order pending quantity."""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import connections, transaction

from apps.parts.models import Part

DIV = "SP"
Q2 = Decimal("0.01")
MAX_RATE = Decimal("99999999.99")  # order1.brate / order1.srate widened to decimal(10,2) (matches amount/amount1)

# Header-level currency -- same free-text convention apps.quotations/
# apps.proforma_invoice already use for their own (per-line) currency field,
# just one value for the whole order here instead of per line. ord_mst.cur /
# ord_mst1.cur (Spare Sale Order) are new, additive-only columns added
# specifically for this (guarded ALTER TABLE, same precedent as
# apps.credit_note's own add_less1_type/rate/code fields on gC_bill).
DEFAULT_CURRENCY = "RS."
CURRENCIES = ("RS.", "USD", "EUR")
_CURRENCY_RE = re.compile(r"^[A-Z.]{1,5}$")


def _clean_currency(raw):
    currency = str(raw or DEFAULT_CURRENCY).strip().upper()
    if not _CURRENCY_RE.match(currency):
        return None
    return currency


class SaleOrderError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _d(value):
    return Decimal(str(value or 0))


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _rows(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exec(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])


def _date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _fy_start(today=None):
    today = today or date.today()
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def _max_order_no_this_fy(cur=None):
    """Order numbers restart each financial year -- old data really does reuse the
    same low numbers across different years (e.g. order "3" exists for both 2021
    and 2022), so "what's the next number" must only ever look at orders dated in
    the CURRENT financial year, never any stored running counter: a counter value
    carried over from last year (or left stranded above reality by a deleted
    order -- delete never decrements it) would both hand out the wrong number.
    Deriving it fresh from the real rows every time is self-correcting on both
    counts, with no FY-rollover step to remember to run each April."""
    sql = "SELECT MAX(CAST([order] AS INT)) FROM ord_mst WHERE ISNUMERIC([order]) = 1 AND ord_date >= %s"
    params = [_fy_start()]
    if cur is None:
        rows = _rows(sql.replace("MAX(CAST([order] AS INT))", "MAX(CAST([order] AS INT)) AS mx"), params)
        return int(rows[0]["mx"]) if rows and rows[0]["mx"] is not None else 0
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def next_no():
    """A preview of the likely next order no. for the Add form -- NOT the
    authoritative allocation (that only happens, locked, inside
    _allocate_order_no(), so two users opening Add at the same moment can't
    both end up saving the same number)."""
    return _max_order_no_this_fy() + 1


def list_orders(start, end, search=""):
    search = (search or "").strip().upper()
    rows = _rows(
        "SELECT o.[div], o.[order], o.ord_date, o.p_code, o.amount1, c.cname, c.cadd3 "
        "FROM ord_mst o LEFT JOIN cust_mst c ON c.ccode = o.p_code "
        "WHERE o.ord_date >= %s AND o.ord_date <= %s ORDER BY o.ord_date, o.[order]",
        [start, end],
    )
    out = []
    for r in rows:
        name = _clean(r["cname"]) or ""
        if search and not name.upper().startswith(search):
            continue
        out.append({
            "div": _clean(r["div"]), "order_no": _clean(r["order"]),
            "date": r["ord_date"].isoformat() if r["ord_date"] else "",
            "party_name": name, "city": _clean(r["cadd3"]) or "",
            "net_amount": f"{_d(r['amount1']):.2f}",
        })
    return out


def load(order_no):
    head = _rows("SELECT * FROM ord_mst WHERE [order] = %s", [str(order_no)])
    if not head:
        return None
    h = head[0]
    party = _rows("SELECT ccode, cname, cadd1, cadd2, cadd3, crep, cr_days FROM cust_mst WHERE ccode = %s", [_clean(h["p_code"])])
    p = party[0] if party else {}
    rep = _rows("SELECT rname FROM rep_mst WHERE rcode = %s", [_clean(p.get("crep")) or ""])
    lines = _rows(
        "SELECT o.i_code, o.stock, o.issue, o.brate, o.cdis, o.cadis, o.cdisam, o.cadisam, o.amount, o.amount1, "
        "o.srate, o.po_no, o.po_dt, o.del_days, o.del_period, o.cr_days, i.i_name "
        "FROM order1 o LEFT JOIN item i ON i.i_code = o.i_code "
        "WHERE o.[order] = %s ORDER BY o.i_code",
        [str(order_no)],
    )
    first = lines[0] if lines else {}
    return {
        "order_no": _clean(h["order"]),
        "order_date": h["ord_date"].isoformat() if h["ord_date"] else "",
        "party_code": _clean(h["p_code"]),
        "party_name": _clean(p.get("cname")) or "",
        "party_address1": _clean(p.get("cadd1")) or "",
        "party_address2": _clean(p.get("cadd2")) or "",
        "city": _clean(p.get("cadd3")) or "",
        "rep_code": _clean(p.get("crep")) or "",
        "rep_name": _clean(rep[0]["rname"]) if rep else "",
        "po_no": _clean(first.get("po_no")) or "",
        "po_date": first["po_dt"].isoformat() if first.get("po_dt") else "",
        "del_days": str(int(_d(first.get("del_days")))),
        "del_period": _clean(first.get("del_period")) or "",
        "cr_days": str(int(_d(first.get("cr_days")))),
        "total": f"{_d(h['amount']):.2f}",
        "discount": f"{_d(h['dis']):.2f}",
        "add_discount": f"{_d(h['adis']):.2f}",
        "net_amount": f"{_d(h['amount1']):.2f}",
        "currency": _clean(h.get("cur")) or DEFAULT_CURRENCY,
        "lines": [{
            "code": _clean(l["i_code"]), "name": _clean(l["i_name"]) or "",
            "dis": f"{_d(l['cdis']):.2f}", "add_dis": f"{_d(l['cadis']):.2f}",
            "qty": f"{int(_d(l['stock']))}", "issued": f"{int(_d(l['issue']))}",
            "rate": f"{_d(l['brate']):.2f}", "s_rate": f"{_d(l['srate']):.2f}",
            "amount": f"{_d(l['amount']):.2f}", "dis_amount": f"{_d(l['cdisam']):.2f}",
            "add_dis_amount": f"{_d(l['cadisam']):.2f}", "net_amount": f"{_d(l['amount1']):.2f}",
        } for l in lines],
    }


def _validate(payload):
    errors = {}
    party = _clean(payload.get("party_code")) or ""
    if not party:
        errors["party_code"] = "Select the party."
    elif not _rows("SELECT ccode FROM cust_mst WHERE ccode = %s", [party]):
        errors["party_code"] = "Party not found."
    lines = []
    for n, row in enumerate(payload.get("lines") or [], start=1):
        code = _clean(row.get("code")) or ""
        if not code:
            continue
        qty = _d(row.get("qty"))
        rate = _d(row.get("rate"))
        if qty <= 0:
            errors["lines"] = f"Row {n}: quantity must be greater than zero."
            break
        if qty != qty.to_integral_value():
            errors["lines"] = f"Row {n}: quantity must be a whole number."
            break
        if rate < 0:
            errors["lines"] = f"Row {n}: rate can't be negative."
            break
        if rate > MAX_RATE:
            errors["lines"] = f"Row {n}: rate can't be more than {MAX_RATE:,.2f} (order1.brate/srate are decimal(7,2))."
            break
        if not _rows("SELECT i_code FROM item WHERE i_code = %s", [code]):
            errors["lines"] = f"Row {n}: item isn't in the Item Master."
            break
        dis = _d(row.get("dis"))
        add_dis = _d(row.get("add_dis"))
        amount = (qty * rate).quantize(Q2, ROUND_HALF_UP)
        dis_amt = (amount * dis / 100).quantize(Q2, ROUND_HALF_UP)
        add_amt = ((amount - dis_amt) * add_dis / 100).quantize(Q2, ROUND_HALF_UP)
        lines.append({
            "code": code, "qty": qty, "rate": rate, "s_rate": _d(row.get("s_rate")),
            "dis": dis, "add_dis": add_dis, "amount": amount, "dis_amount": dis_amt,
            "add_dis_amount": add_amt, "net_amount": amount - dis_amt - add_amt,
        })
    if not lines and "lines" not in errors:
        errors["lines"] = "Add at least one item."
    if errors:
        raise SaleOrderError("Fix the highlighted fields.", errors)
    return party, lines


def _allocate_order_no(cur):
    """The real, locked allocation used inside save()'s own transaction -- next_no()
    above is only an unlocked preview for the Add form. `SELECT ... WITH (UPDLOCK,
    HOLDLOCK)` (SQL Server's equivalent of `SELECT ... FOR UPDATE`) holds the single
    inv_no row locked for the rest of the transaction, so a second concurrent Add
    blocks here until the first commits its new order_no, instead of both computing
    the same next number (the same race apps.returnable_challan/apps.mrn/etc. avoid
    by locking their own counter row the same way via select_for_update()). The row
    is only ever locked here, never read -- the actual next number always comes
    from _max_order_no_this_fy(), for the same reason next_no() does (see there)."""
    cur.execute("SELECT sp_ord_no FROM inv_no WITH (UPDLOCK, HOLDLOCK)")
    cur.fetchone()
    return str(_max_order_no_this_fy(cur) + 1)


def save(payload, mode, username=""):
    if not writes_enabled():
        raise SaleOrderError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    order_no = str(payload.get("order_no") or "").strip() if mode != "add" else None
    if mode != "add" and not order_no:
        raise SaleOrderError("Enter the order no.", {"order_no": "Enter the order no."})

    if mode == "delete":
        # Delete only ever sends order_no -- running the add/modify field validation
        # (party, line items, ...) against that bare payload would always fail.
        with transaction.atomic(using="legacy"):
            if not _rows("SELECT [order] FROM ord_mst WHERE [order] = %s", [order_no]):
                raise SaleOrderError(f"Order {order_no} not found.", {"order_no": "Order not found."})
            for o in _rows("SELECT i_code, stock FROM order1 WHERE [order] = %s", [order_no]):
                _exec("UPDATE item SET [order] = COALESCE([order], 0) - %s WHERE i_code = %s",
                      [o["stock"], _clean(o["i_code"])])
            _exec("DELETE FROM order1 WHERE [order] = %s", [order_no])
            _exec("DELETE FROM ord_mst WHERE [order] = %s", [order_no])
        return {"order_no": order_no}

    order_date = _date(payload.get("order_date")) or date.today()
    party, lines = _validate(payload)
    currency = _clean_currency(payload.get("currency"))
    if currency is None:
        raise SaleOrderError("Fix the highlighted fields.",
                             {"currency": "Currency must be up to 5 letters (e.g. RS., USD)."})
    cust = _rows("SELECT crep, cstate FROM cust_mst WHERE ccode = %s", [party])[0]
    po_no = _clean(payload.get("po_no")) or ""
    po_date = _date(payload.get("po_date"))
    del_days = int(_d(payload.get("del_days")))
    del_period = _clean(payload.get("del_period")) or ""
    cr_days = int(_d(payload.get("cr_days")))
    total = sum((l["amount"] for l in lines), Decimal("0"))
    discount = sum((l["dis_amount"] for l in lines), Decimal("0"))
    add_discount = sum((l["add_dis_amount"] for l in lines), Decimal("0"))
    net = sum((l["net_amount"] for l in lines), Decimal("0"))
    user = (username or "")[:10]

    with transaction.atomic(using="legacy"):
        if mode == "modify":
            if not _rows("SELECT [order] FROM ord_mst WHERE [order] = %s", [order_no]):
                raise SaleOrderError(f"Order {order_no} not found.", {"order_no": "Order not found."})
            for o in _rows("SELECT i_code, stock FROM order1 WHERE [order] = %s", [order_no]):
                _exec("UPDATE item SET [order] = COALESCE([order], 0) - %s WHERE i_code = %s",
                      [o["stock"], _clean(o["i_code"])])
            _exec("DELETE FROM order1 WHERE [order] = %s", [order_no])
            _exec("DELETE FROM ord_mst WHERE [order] = %s", [order_no])
        else:
            with connections["legacy"].cursor() as cur:
                order_no = _allocate_order_no(cur)
                cur.execute("UPDATE inv_no SET sp_ord_no = %s", [int(order_no)])

        for l in lines:
            adj = "Y" if l["qty"] == Decimal("0") else None
            _exec(
                "INSERT INTO order1 ([div], [order], [date], i_code, p_code, stock, brate, cdis, cadis, po_no, po_dt, "
                "rep_code, ar_code, issue, adj, amount, amount1, mcode, cdisam, cadisam, del_days, uname, del_period, "
                "cr_days, srate) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [DIV, order_no, order_date, l["code"], party, l["qty"], l["rate"], l["dis"], l["add_dis"],
                 po_no, po_date, _clean(cust["crep"]), _clean(cust["cstate"]), Decimal("0"), adj,
                 l["amount"], l["net_amount"], "", l["dis_amount"], l["add_dis_amount"], del_days, user,
                 del_period, cr_days, l["s_rate"]],
            )
            _exec("UPDATE item SET [order] = COALESCE([order], 0) + %s WHERE i_code = %s", [l["qty"], l["code"]])
        _exec(
            "INSERT INTO ord_mst ([div], [order], ord_date, p_code, amount, amount1, dis, adis, mcode, del_by, uname, cur) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [DIV, order_no, order_date, party, total, net, discount, add_discount, "", "", user, currency],
        )
        _exec("UPDATE inv_no SET sp_ord_no = %s WHERE sp_ord_no < %s", [int(order_no), int(order_no)])
    return {"order_no": order_no}


def item_detail(code):
    rows = _rows("SELECT i_code, i_name, unit, rate FROM item WHERE i_code = %s", [code.strip().upper()])
    if not rows:
        return None
    r = rows[0]
    part = Part.objects.filter(part_number=_clean(r["i_code"])).first()
    stock = part.current_stock if part and part.current_stock is not None else Decimal("0")
    return {"code": _clean(r["i_code"]), "name": _clean(r["i_name"]) or "", "unit": _clean(r["unit"]) or "",
            "rate": f"{_d(r['rate']):.2f}", "stock": f"{_d(stock):.3f}"}


def party_detail(code):
    rows = _rows("SELECT ccode, cname, cadd3, crep, cdis, cadis, cr_days FROM cust_mst WHERE ccode = %s",
                 [code.strip().upper()])
    if not rows:
        return None
    r = rows[0]
    rep = _rows("SELECT rname FROM rep_mst WHERE rcode = %s", [_clean(r["crep"]) or ""])
    return {"code": _clean(r["ccode"]), "name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or "",
            "rep_code": _clean(r["crep"]) or "", "rep_name": _clean(rep[0]["rname"]) if rep else "",
            "dis": f"{_d(r['cdis']):.2f}", "add_dis": f"{_d(r['cadis']):.2f}",
            "cr_days": str(int(_d(r["cr_days"])))}


def sale_report(start, end):
    rows = list_orders(start, end)
    total = sum((_d(r["net_amount"]) for r in rows), Decimal("0"))
    return {"rows": rows, "total": f"{total:.2f}"}


def party_pending(as_on, party_code=None):
    from apps.parts.models import Part

    items = {r["i_code"].strip(): r for r in _rows("SELECT i_code, i_name, rate FROM item") if r["i_code"]}
    custs = {r["ccode"].strip(): r for r in _rows("SELECT ccode, cname, cadd3, cdis FROM cust_mst") if r["ccode"]}
    current = {p.part_number.strip(): _d(p.current_stock) for p in Part.objects.all() if p.part_number}
    sql = ("SELECT [order], date, i_code, p_code, stock, issue FROM order1 "
           "WHERE COALESCE(adj, '') <> 'Y' AND date <= %s AND (stock - issue) > 0")
    params = [as_on]
    if party_code:
        sql += " AND p_code = %s"
        params.append(party_code)
    sql += " ORDER BY p_code, date, [order]"
    groups, grand = [], Decimal("0")
    current_party, bucket = None, None
    for r in _rows(sql, params):
        code = (r["p_code"] or "").strip()
        if code != current_party:
            cust = custs.get(code, {})
            bucket = {"party_code": code, "party_name": _clean(cust.get("cname")) or "",
                      "city": _clean(cust.get("cadd3")) or "", "lines": [], "total": Decimal("0")}
            groups.append(bucket)
            current_party = code
        item_code = (r["i_code"] or "").strip()
        item = items.get(item_code, {})
        pending_qty = _d(r["stock"]) - _d(r["issue"])
        gross = _d(item.get("rate")) * pending_qty
        disc = gross * _d(custs.get(code, {}).get("cdis")) / 100
        value = gross - disc
        bucket["lines"].append({
            "order_no": _clean(r["order"]), "date": r["date"].isoformat() if r["date"] else "",
            "item_code": item_code, "item_name": _clean(item.get("i_name")) or "",
            "pending": f"{pending_qty:.3f}", "current": f"{current.get(item_code, Decimal('0')):.3f}",
            "value": f"{value:.2f}",
        })
        bucket["total"] += value
        grand += value
    for g in groups:
        g["total"] = f"{g['total']:.2f}"
    return {"groups": groups, "grand_total": f"{grand:.2f}"}


def item_pending(as_on, item_code=None):
    from apps.parts.models import Part

    items = {r["i_code"].strip(): r for r in _rows("SELECT i_code, i_name FROM item") if r["i_code"]}
    custs = {r["ccode"].strip(): r for r in _rows("SELECT ccode, cname, cadd3 FROM cust_mst") if r["ccode"]}
    current = {p.part_number.strip(): _d(p.current_stock) for p in Part.objects.all() if p.part_number}
    sql = ("SELECT [order], date, i_code, p_code, stock, issue FROM order1 "
           "WHERE COALESCE(adj, '') <> 'Y' AND date <= %s AND (stock - issue) > 0")
    params = [as_on]
    if item_code:
        sql += " AND i_code = %s"
        params.append(item_code)
    sql += " ORDER BY i_code, date, [order]"
    groups, grand = [], Decimal("0")
    current_item, bucket = None, None
    for r in _rows(sql, params):
        code = (r["i_code"] or "").strip()
        if code != current_item:
            info = items.get(code, {})
            bucket = {"item_code": code, "item_name": _clean(info.get("i_name")) or "",
                      "current": f"{current.get(code, Decimal('0')):.3f}", "lines": [], "total": Decimal("0")}
            groups.append(bucket)
            current_item = code
        pending_qty = _d(r["stock"]) - _d(r["issue"])
        cust = custs.get((r["p_code"] or "").strip(), {})
        bucket["lines"].append({
            "order_no": _clean(r["order"]), "date": r["date"].isoformat() if r["date"] else "",
            "party_name": _clean(cust.get("cname")) or "", "city": _clean(cust.get("cadd3")) or "",
            "pending": f"{pending_qty:.3f}",
        })
        bucket["total"] += pending_qty
        grand += pending_qty
    for g in groups:
        g["total"] = f"{g['total']:.3f}"
    return {"groups": groups, "grand_total": f"{grand:.3f}"}


def areas(term=""):
    term = (term or "").strip().upper()
    rows = _rows("SELECT stcode, stname FROM state ORDER BY stname")
    out = [{"code": _clean(r["stcode"]), "name": _clean(r["stname"]) or ""} for r in rows if r["stcode"]]
    if term:
        out = [a for a in out if term in a["name"].upper() or term in a["code"].upper()]
    return out


def area_pending(as_on, area_code=None):
    from apps.parts.models import Part

    items = {r["i_code"].strip(): r for r in _rows("SELECT i_code, i_name FROM item") if r["i_code"]}
    custs = {r["ccode"].strip(): r for r in _rows("SELECT ccode, cname, cadd3 FROM cust_mst") if r["ccode"]}
    area_names = {a["code"]: a["name"] for a in areas()}
    sql = ("SELECT [order], date, i_code, p_code, ar_code, stock, issue FROM order1 "
           "WHERE COALESCE(adj, '') <> 'Y' AND date <= %s AND (stock - issue) > 0")
    params = [as_on]
    if area_code:
        sql += " AND ar_code = %s"
        params.append(area_code)
    sql += " ORDER BY ar_code, p_code, date, [order]"
    groups, grand = [], Decimal("0")
    current_area, current_party, area_bucket, party_bucket = None, None, None, None
    for r in _rows(sql, params):
        area = (r["ar_code"] or "").strip()
        party = (r["p_code"] or "").strip()
        if area != current_area:
            area_bucket = {"area_code": area, "area_name": area_names.get(area, ""), "parties": [], "total": Decimal("0")}
            groups.append(area_bucket)
            current_area, current_party = area, None
        if party != current_party:
            cust = custs.get(party, {})
            party_bucket = {"party_code": party, "party_name": _clean(cust.get("cname")) or "",
                            "city": _clean(cust.get("cadd3")) or "", "lines": []}
            area_bucket["parties"].append(party_bucket)
            current_party = party
        pending_qty = _d(r["stock"]) - _d(r["issue"])
        item_code = (r["i_code"] or "").strip()
        party_bucket["lines"].append({
            "order_no": _clean(r["order"]), "date": r["date"].isoformat() if r["date"] else "",
            "item_code": item_code, "item_name": _clean(items.get(item_code, {}).get("i_name")) or "",
            "pending": f"{pending_qty:.3f}",
        })
        area_bucket["total"] += pending_qty
        grand += pending_qty
    for g in groups:
        g["total"] = f"{g['total']:.3f}"
    return {"groups": groups, "grand_total": f"{grand:.3f}"}


def reps(term=""):
    term = (term or "").strip().upper()
    rows = _rows("SELECT rcode, rname FROM rep_mst ORDER BY rname")
    out = [{"code": _clean(r["rcode"]), "name": _clean(r["rname"]) or ""} for r in rows if r["rcode"]]
    if term:
        out = [a for a in out if term in a["name"].upper() or term in a["code"].upper()]
    return out


def rep_orders(start, end, rep_code=None, pending=False):
    names = {r["code"]: r["name"] for r in reps()}
    custs = {r["ccode"].strip(): r for r in _rows("SELECT ccode, cname, cadd3 FROM cust_mst") if r["ccode"]}
    sql = ("SELECT div, [order], date, p_code, rep_code, stock, issue, brate, cdis, cadis FROM order1 "
           "WHERE date >= %s AND date <= %s AND rep_code IS NOT NULL")
    params = [start, end]
    if pending:
        sql += " AND COALESCE(adj, '') <> 'Y' AND (stock - issue) > 0"
    if rep_code:
        sql += " AND rep_code = %s"
        params.append(rep_code)
    sql += " ORDER BY rep_code, div, p_code, [order], date"
    groups, grand = [], Decimal("0")
    current_rep, current_order, group, order = None, None, None, None
    for r in _rows(sql, params):
        rep = (r["rep_code"] or "").strip()
        key = (r["div"], r["order"], (r["p_code"] or "").strip(), r["date"])
        if rep != current_rep:
            group = {"rep_code": rep, "rep_name": names.get(rep, ""), "orders": [], "total": Decimal("0")}
            groups.append(group)
            current_rep, current_order = rep, None
        if key != current_order:
            cust = custs.get(key[2], {})
            order = {"div": _clean(key[0]) or "", "order_no": _clean(key[1]) or "",
                     "date": key[3].isoformat() if key[3] else "", "party_name": _clean(cust.get("cname")) or "",
                     "city": _clean(cust.get("cadd3")) or "", "amount": Decimal("0")}
            group["orders"].append(order)
            current_order = key
        qty = _d(r["stock"]) - _d(r["issue"]) if pending else _d(r["stock"])
        tamt = (qty * _d(r["brate"])).quantize(Q2, ROUND_HALF_UP)
        tdis = (tamt * _d(r["cdis"]) / 100).quantize(Q2, ROUND_HALF_UP)
        tadis = ((tamt - tdis) * _d(r["cadis"]) / 100).quantize(Q2, ROUND_HALF_UP)
        order["amount"] += tamt - tdis - tadis
        group["total"] += tamt - tdis - tadis
        grand += tamt - tdis - tadis
    for g in groups:
        for o in g["orders"]:
            o["amount"] = f"{o['amount']:.2f}"
        g["total"] = f"{g['total']:.2f}"
    return {"groups": groups, "grand_total": f"{grand:.2f}"}


def despatch_status(as_on):
    custs = {r["ccode"].strip(): r for r in _rows("SELECT ccode, cname FROM cust_mst") if r["ccode"]}
    rows = _rows("SELECT div, [order], date, p_code, stock, brate, cdis, cadis, del_days FROM order1 "
                 "WHERE COALESCE(adj, '') <> 'Y' AND DATEADD(day, COALESCE(del_days, 0), [date]) <= %s "
                 "ORDER BY [order], date", [as_on])
    orders, current = [], None
    for r in rows:
        key = (r["div"], r["order"], r["date"])
        if key != current:
            due = r["date"] + timedelta(days=int(_d(r["del_days"]))) if r["date"] else None
            cust = custs.get((r["p_code"] or "").strip(), {})
            current_order = {"party_name": _clean(cust.get("cname")) or "", "order_no": f"{_clean(r['div'])}{_clean(r['order'])}",
                             "order_date": r["date"].isoformat() if r["date"] else "",
                             "despatch_date": due.isoformat() if due else "", "amount": Decimal("0")}
            orders.append(current_order)
            current = key
        tamt = (_d(r["stock"]) * _d(r["brate"])).quantize(Q2, ROUND_HALF_UP)
        tdis = (tamt * _d(r["cdis"]) / 100).quantize(Q2, ROUND_HALF_UP)
        current_order["amount"] += tamt - tdis
    total = sum((o["amount"] for o in orders), Decimal("0"))
    for o in orders:
        o["amount"] = f"{o['amount']:.2f}"
    return {"orders": orders, "total": f"{total:.2f}"}


def adjustment_lines(party_code, as_on):
    items = {r["i_code"].strip(): r for r in _rows("SELECT i_code, i_name FROM item") if r["i_code"]}
    rows = _rows("SELECT div, [order], date, i_code, stock, issue FROM order1 "
                 "WHERE p_code = %s AND COALESCE(adj, '') <> 'Y' AND (stock - issue) > 0 AND date <= %s "
                 "ORDER BY date, [order]", [party_code, as_on])
    out = []
    for r in rows:
        code = (r["i_code"] or "").strip()
        out.append({
            "order_no": _clean(r["order"]), "div": _clean(r["div"]) or "",
            "order_date": r["date"].isoformat() if r["date"] else "",
            "item_code": code, "item_name": _clean(items.get(code, {}).get("i_name")) or "",
            "ordered": f"{_d(r['stock']):.3f}", "issued": f"{_d(r['issue']):.3f}",
            "pending": f"{_d(r['stock']) - _d(r['issue']):.3f}",
        })
    return out


def adjust_orders(party_code, lines):
    if not writes_enabled():
        raise SaleOrderError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    count = 0
    with transaction.atomic(using="legacy"):
        for l in lines:
            _exec("UPDATE order1 SET adj = 'Y', adj1 = 'Y' WHERE p_code = %s AND [order] = %s AND div = %s "
                  "AND i_code = %s AND COALESCE(adj, '') <> 'Y'",
                  [party_code, l["order_no"], l["div"], l["item_code"]])
            count += 1
    return count


def adjustment_report(as_on, party_code=None):
    items = {r["i_code"].strip(): r for r in _rows("SELECT i_code, i_name FROM item") if r["i_code"]}
    custs = {r["ccode"].strip(): r for r in _rows("SELECT ccode, cname, cadd3, cdis FROM cust_mst") if r["ccode"]}
    sql = ("SELECT [order], date, i_code, p_code, stock, issue, brate FROM order1 "
           "WHERE COALESCE(adj1, '') = 'Y' AND date <= %s AND (stock - issue) > 0")
    params = [as_on]
    if party_code:
        sql += " AND p_code = %s"
        params.append(party_code)
    sql += " ORDER BY p_code, date, [order]"
    groups, grand = [], Decimal("0")
    current, bucket = None, None
    for r in _rows(sql, params):
        code = (r["p_code"] or "").strip()
        if code != current:
            cust = custs.get(code, {})
            bucket = {"party_code": code, "party_name": _clean(cust.get("cname")) or "",
                      "city": _clean(cust.get("cadd3")) or "", "lines": [], "total": Decimal("0")}
            groups.append(bucket)
            current = code
        qty = _d(r["stock"]) - _d(r["issue"])
        item_code = (r["i_code"] or "").strip()
        gross = _d(r["brate"]) * qty
        value = gross - gross * _d(custs.get(code, {}).get("cdis")) / 100
        bucket["lines"].append({
            "order_no": _clean(r["order"]), "date": r["date"].isoformat() if r["date"] else "",
            "item_code": item_code, "item_name": _clean(items.get(item_code, {}).get("i_name")) or "",
            "pending": f"{qty:.3f}", "value": f"{value:.2f}",
        })
        bucket["total"] += value
        grand += value
    for g in groups:
        g["total"] = f"{g['total']:.2f}"
    return {"groups": groups, "grand_total": f"{grand:.2f}"}


def _spare_max_order_no_this_fy():
    """Same FY-scoped-not-lifetime convention as _max_order_no_this_fy() above,
    for the Spare Sale Order's own separate ord_mst1/sp_ord1 numbering."""
    rows = _rows(
        "SELECT MAX(CAST(ord_no AS INT)) AS mx FROM ord_mst1 WHERE ISNUMERIC(ord_no) = 1 AND ord_date >= %s",
        [_fy_start()],
    )
    return int(rows[0]["mx"]) if rows and rows[0]["mx"] is not None else 0


def spare_next_no():
    return _spare_max_order_no_this_fy() + 1


def spare_list(start, end, search=""):
    search = (search or "").strip().upper()
    rows = _rows(
        "SELECT o.ord_no, o.div, o.ord_date, o.p_code, o.amount1, c.cname, c.cadd3 FROM ord_mst1 o "
        "LEFT JOIN cust_mst c ON c.ccode = o.p_code WHERE o.ord_date >= %s AND o.ord_date <= %s "
        "ORDER BY o.ord_date, o.ord_no", [start, end])
    out = []
    for r in rows:
        name = _clean(r["cname"]) or ""
        if search and not name.upper().startswith(search):
            continue
        order_no, div = _clean(r["ord_no"]), _clean(r["div"])
        out.append({"order_no": order_no, "div": div, "key": f"{order_no}|{div}",
                    "date": r["ord_date"].isoformat() if r["ord_date"] else "",
                    "party_name": name, "city": _clean(r["cadd3"]) or "", "amount": f"{_d(r['amount1']):.2f}"})
    return out


def spare_load(ord_no, div=None):
    """div disambiguates which physical row to open when ord_no collides
    across divisions -- see spare_save()/_spare_reverse()'s own notes on this
    (ord_no is only unique within a financial year, old div='' historical
    rows can share a number with a new div='SP' one). Left optional so a
    caller without a specific row still gets the previous (first-match)
    behaviour rather than breaking outright on old historical orders."""
    where = ["ord_no = %s"]
    params = [str(ord_no)]
    if div is not None:
        where.append("div = %s")
        params.append(div)
    head = _rows("SELECT * FROM ord_mst1 WHERE " + " AND ".join(where), params)
    if not head:
        return None
    h = head[0]
    cust = _rows("SELECT ccode, cname, cadd1, cadd2, cadd3, cphno, cstat, crep FROM cust_mst WHERE ccode = %s", [_clean(h["p_code"])])
    c = cust[0] if cust else {}
    rep = _rows("SELECT rname FROM rep_mst WHERE rcode = %s", [_clean(c.get("crep")) or ""])
    lines_where = ["ord_no = %s"]
    lines_params = [str(ord_no)]
    if div is not None:
        lines_where.append("dv_code = %s")
        lines_params.append(div)
    lines = _rows("SELECT i_code, qty_ord, rate, dis, amount FROM ord_dat WHERE " + " AND ".join(lines_where) + " ORDER BY i_code", lines_params)
    names = {r["icod"].strip(): r["ides"] for r in _rows("SELECT icod, ides FROM [part-mst]") if r["icod"]}
    return {
        "order_no": _clean(h["ord_no"]), "div": _clean(h["div"]),
        "order_date": h["ord_date"].isoformat() if h["ord_date"] else "",
        "party_code": _clean(h["p_code"]), "party_name": _clean(c.get("cname")) or "",
        "city": _clean(c.get("cadd3")) or "", "address1": _clean(c.get("cadd1")) or "",
        "address2": _clean(c.get("cadd2")) or "", "phone": _clean(c.get("cphno")) or "",
        "rep_code": _clean(c.get("crep")) or "", "rep_name": _clean(rep[0]["rname"]) if rep else "",
        "state": _clean(c.get("cstat")) or "", "po_no": _clean(h["ordn"]) or "",
        "po_date": h["ord_dt1"].isoformat() if h["ord_dt1"] else "",
        "remarks": _clean(h["remk"]) or "", "remarks1": _clean(h["remk1"]) or "",
        "total": f"{_d(h['amount']):.2f}", "discount": f"{_d(h['dis']):.2f}",
        # ord_mst1.adis stores an AMOUNT, not a %, and is order-wide (no per-line
        # column exists on ord_dat for it) -- the ADDL.DIS% input only ever applies
        # once, to the order subtotal. The % itself isn't persisted, only this amount.
        "add_discount": f"{_d(h['adis']):.2f}",
        "net_amount": f"{_d(h.get('amount1', h['amount'])):.2f}",
        "currency": _clean(h.get("cur")) or DEFAULT_CURRENCY,
        "lines": [{"code": _clean(l["i_code"]), "name": _clean(names.get((l["i_code"] or "").strip())) or "",
                   "qty": f"{_d(l['qty_ord']):.3f}", "rate": f"{_d(l['rate']):.2f}", "dis": f"{_d(l['dis']):.2f}",
                   "amount": f"{_d(l['amount']):.2f}"} for l in lines],
    }


def spare_item(code):
    rows = _rows("SELECT icod, ides, srate FROM [part-mst] WHERE icod = %s", [code.strip().upper()])
    if not rows:
        return None
    r = rows[0]
    return {"code": _clean(r["icod"]), "name": _clean(r["ides"]) or "", "rate": f"{_d(r['srate']):.2f}"}


def _spare_reverse(ord_no):
    # Scoped by division (ord_dat.dv_code / ord_mst1.div, both always 'SP' for
    # rows this app itself wrote -- see spare_save's own INSERTs below) for the
    # same reason as spare_save's own existence checks: ord_no collides with
    # old, unrelated historical orders from a different division/year, and an
    # unscoped DELETE here would silently wipe or reverse stock against the
    # wrong order entirely.
    for l in _rows("SELECT i_code, qty_ord FROM ord_dat WHERE ord_no = %s AND dv_code = %s", [ord_no, DIV]):
        _exec("UPDATE [part-mst] SET [order] = COALESCE([order], 0) - %s WHERE icod = %s",
              [l["qty_ord"], _clean(l["i_code"])])
    _exec("DELETE FROM ord_dat WHERE ord_no = %s AND dv_code = %s", [ord_no, DIV])
    _exec("DELETE FROM ord_mst1 WHERE ord_no = %s AND div = %s", [ord_no, DIV])


def spare_save(payload, mode, username=""):
    if not writes_enabled():
        raise SaleOrderError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    if mode == "add":
        ord_no = str(spare_next_no())
    else:
        ord_no = str(payload.get("order_no") or "").strip()
        if not ord_no:
            raise SaleOrderError("Enter the order no.", {"order_no": "Enter the order no."})
    if mode == "delete":
        with transaction.atomic(using="legacy"):
            if not _rows("SELECT ord_no FROM ord_mst1 WHERE ord_no = %s AND div = %s", [ord_no, DIV]):
                raise SaleOrderError(f"Order {ord_no} not found.")
            _spare_reverse(ord_no)
        return {"order_no": ord_no}

    order_date = _date(payload.get("order_date")) or date.today()
    party = _clean(payload.get("party_code")) or ""
    errors = {}
    if not party or not _rows("SELECT ccode FROM cust_mst WHERE ccode = %s", [party]):
        errors["party_code"] = "Select the party."
    lines = []
    for n, row in enumerate(payload.get("lines") or [], start=1):
        code = _clean(row.get("code")) or ""
        if not code:
            continue
        qty = _d(row.get("qty"))
        rate = _d(row.get("rate"))
        dis = _d(row.get("dis")) or Decimal("0")
        if qty <= 0:
            errors["lines"] = f"Row {n}: quantity must be greater than zero."
            break
        if dis < 0 or dis > 100:
            errors["lines"] = f"Row {n}: discount % must be between 0 and 100."
            break
        if not _rows("SELECT icod FROM [part-mst] WHERE icod = %s", [code]):
            errors["lines"] = f"Row {n}: item isn't in the Item Master."
            break
        gross = (qty * rate).quantize(Q2, ROUND_HALF_UP)
        lines.append({"code": code, "qty": qty, "rate": rate, "dis": dis, "amount": gross})
    if not lines and "lines" not in errors:
        errors["lines"] = "Add at least one item."
    currency = _clean_currency(payload.get("currency"))
    if currency is None:
        errors["currency"] = "Currency must be up to 5 letters (e.g. RS., USD)."
    if errors:
        raise SaleOrderError("Fix the highlighted fields.", errors)
    gross_total = sum((l["amount"] for l in lines), Decimal("0"))
    line_dis_total = sum(((l["amount"] * l["dis"] / 100).quantize(Q2, ROUND_HALF_UP) for l in lines), Decimal("0"))
    subtotal = gross_total - line_dis_total
    addl_dis_pct = _d(payload.get("addl_dis_pct")) or Decimal("0")
    addl_dis_amt = (subtotal * addl_dis_pct / 100).quantize(Q2, ROUND_HALF_UP)
    net_total = subtotal - addl_dis_amt
    user = (username or "")[:10]
    po_no = _clean(payload.get("po_no")) or ""
    po_date = _date(payload.get("po_date"))
    with transaction.atomic(using="legacy"):
        if mode in ("modify",):
            if not _rows("SELECT ord_no FROM ord_mst1 WHERE ord_no = %s AND div = %s", [ord_no, DIV]):
                raise SaleOrderError(f"Order {ord_no} not found.")
            _spare_reverse(ord_no)
        # Scoped by div too -- ord_no is only unique within the current FY
        # (see spare_next_no()/_spare_max_order_no_this_fy()), but old
        # historical rows (div='', predating this app's own div='SP' numbering)
        # can still carry the same number from a different year. An unscoped
        # check here false-positived "Order No. 1 already exists" on the very
        # first Add of a new financial year, since spare_next_no() legitimately
        # restarts from 1 once no current-FY orders exist yet, and that 1
        # collided with an old, unrelated historical order. New orders from
        # this app are always div='SP' (see the INSERT below), so that's the
        # only real conflict that matters.
        elif _rows("SELECT ord_no FROM ord_mst1 WHERE ord_no = %s AND div = %s", [ord_no, DIV]):
            raise SaleOrderError(f"Order No. {ord_no} already exists.", {"order_no": "Order No. already exists."})
        for l in lines:
            _exec("INSERT INTO ord_dat (ord_no, ord_dt, p_code, i_code, dis, qty_ord, rate, qty_iss, adj, amount, "
                  "dv_code, ordn, ord_dt1) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  [ord_no, order_date, party, l["code"], l["dis"], l["qty"], l["rate"], Decimal("0"), None,
                   l["amount"], DIV, po_no, po_date])
            _exec("UPDATE [part-mst] SET [order] = COALESCE([order], 0) + %s WHERE icod = %s", [l["qty"], l["code"]])
        _exec("INSERT INTO ord_mst1 (div, ord_no, ord_date, p_code, amount, amount1, dis, adis, mcode, del_by, uname, "
              "remk, remk1, ordn, ord_dt1, cur) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
              [DIV, ord_no, order_date, party, gross_total, net_total, line_dis_total, addl_dis_amt, "", "", user,
               _clean(payload.get("remarks"))[:40] if payload.get("remarks") else "",
               _clean(payload.get("remarks1"))[:40] if payload.get("remarks1") else "", po_no, po_date, currency])
        _exec("UPDATE inv_no SET sp_ord1 = %s WHERE sp_ord1 < %s", [int(ord_no), int(ord_no)])
    return {"order_no": ord_no}


def spare_party_pending(party_code=None):
    names = {r["icod"].strip(): r["ides"] for r in _rows("SELECT icod, ides FROM [part-mst]") if r["icod"]}
    custs = {r["ccode"].strip(): r for r in _rows("SELECT ccode, cname, cadd3 FROM cust_mst") if r["ccode"]}
    sql = ("SELECT ord_no, ord_dt, p_code, i_code, qty_ord, qty_iss FROM ord_dat "
           "WHERE (qty_ord - qty_iss) > 0 AND COALESCE(adj, '') <> 'Y'")
    params = []
    if party_code:
        sql += " AND p_code = %s"
        params.append(party_code)
    sql += " ORDER BY p_code, ord_no"
    groups, grand = [], Decimal("0")
    current, bucket = None, None
    for r in _rows(sql, params):
        code = (r["p_code"] or "").strip()
        if code != current:
            cust = custs.get(code, {})
            bucket = {"party_code": code, "party_name": _clean(cust.get("cname")) or "",
                      "city": _clean(cust.get("cadd3")) or "", "lines": [], "total": Decimal("0")}
            groups.append(bucket)
            current = code
        item_code = (r["i_code"] or "").strip()
        pending = _d(r["qty_ord"]) - _d(r["qty_iss"])
        bucket["lines"].append({
            "order_no": _clean(r["ord_no"]), "date": r["ord_dt"].isoformat() if r["ord_dt"] else "",
            "item_code": item_code, "item_name": _clean(names.get(item_code)) or "",
            "ordered": f"{_d(r['qty_ord']):.3f}", "issued": f"{_d(r['qty_iss']):.3f}", "pending": f"{pending:.3f}",
        })
        bucket["total"] += pending
        grand += pending
    for g in groups:
        g["total"] = f"{g['total']:.3f}"
    return {"groups": groups, "grand_total": f"{grand:.3f}"}


def spare_item_pending(item_code=None):
    names = {r["icod"].strip(): r["ides"] for r in _rows("SELECT icod, ides FROM [part-mst]") if r["icod"]}
    sql = "SELECT i_code, SUM(qty_ord - qty_iss) AS pending FROM ord_dat WHERE (qty_ord - qty_iss) > 0 AND COALESCE(adj, '') <> 'Y'"
    params = []
    if item_code:
        sql += " AND i_code = %s"
        params.append(item_code)
    sql += " GROUP BY i_code ORDER BY i_code"
    rows, grand = [], Decimal("0")
    for r in _rows(sql, params):
        code = (r["i_code"] or "").strip()
        pending = _d(r["pending"])
        rows.append({"item_code": code, "item_name": _clean(names.get(code)) or "", "pending": f"{pending:.3f}"})
        grand += pending
    return {"rows": rows, "grand_total": f"{grand:.3f}"}


def spare_adjustment_lines(party_code):
    names = {r["icod"].strip(): r["ides"] for r in _rows("SELECT icod, ides FROM [part-mst]") if r["icod"]}
    rows = _rows("SELECT ord_no, ord_dt, i_code, qty_ord, qty_iss FROM ord_dat "
                 "WHERE p_code = %s AND (qty_ord - qty_iss) > 0 AND COALESCE(adj, '') <> 'Y' "
                 "ORDER BY ord_dt, ord_no", [party_code])
    out = []
    for r in rows:
        code = (r["i_code"] or "").strip()
        out.append({
            "order_no": _clean(r["ord_no"]), "div": "", "order_date": r["ord_dt"].isoformat() if r["ord_dt"] else "",
            "item_code": code, "item_name": _clean(names.get(code)) or "",
            "ordered": f"{_d(r['qty_ord']):.3f}", "issued": f"{_d(r['qty_iss']):.3f}",
            "pending": f"{_d(r['qty_ord']) - _d(r['qty_iss']):.3f}",
        })
    return out


def spare_adjust(party_code, lines):
    if not writes_enabled():
        raise SaleOrderError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")
    count = 0
    with transaction.atomic(using="legacy"):
        for l in lines:
            _exec("UPDATE ord_dat SET adj = 'Y' WHERE p_code = %s AND ord_no = %s AND i_code = %s "
                  "AND COALESCE(adj, '') <> 'Y'", [party_code, l["order_no"], l["item_code"]])
            count += 1
    return count

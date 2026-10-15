"""
Spare Part Invoice (old VFP form "gstbill7" / list "GST BILLING (Spear Part)").

Header lives in the SAME ``bill`` table as apps.gst_invoice ('G' type), this time
``bill_type = 'P'`` -- confirmed against live data (56 real 'G' rows, 144 real 'P'
rows). The two types also share the very same ``inv_no.gb_inv_no`` numbering
counter (the real VFP source for both forms runs the identical
``nn=allt(str(gb_inv_no+1))`` against that one column), so bill numbers are unique
across both types together, never just within one -- ``next_no()``/``_allocate_no()``
below deliberately read/lock that same column apps.gst_invoice.services does.

Line items live in ``imaster`` (apps.purchase_orders.models.ItemMasterTransaction's
table) -- NOT ``i_master`` (underscore), which is what GST Billing ('G') uses and
which has zero 'P' rows. Items are looked up against ``part-mst``
(apps.parts.models.Part), not the ``item`` table GST Billing uses.

Confirmed from the real VFP save/delete routines (``rpldata``/``deldata``), this
form -- unlike GST Billing -- really does:
  * Decrement ``part-mst.cur_stk`` by each line's qty on save, restore it on delete.
  * Increment the matching ``ord_dat.qty_iss`` (by party+order no+item code) when a
    line carries an ORDER NO, decrement it back on delete/modify.
  * Post real ``trans``/``vno`` ledger entries, same GST-bucket pattern as GST
    Billing, but freight is always credited to the fixed ledger codes "F001"
    (freight) / "F003" (GST on freight) -- hardcoded literals in the VFP source,
    not an operator-entered code like GST Billing's freight fields.

Deliberately NOT implemented (flagged, not guessed):
  * The rounding-difference ledger line (VFP global ``pdiffcode``) -- same
    unresolved gap as apps.credit_note.narration_services and apps.gst_invoice;
    no Django-side value for it has been confirmed for this table/bill_type.
  * Pulling pending GST Returnable Challan lines into an invoice (VFP: items
    already in ``imaster`` with a ``chl_no`` and no ``bill_no`` get re-assigned
    here instead of inserted fresh, and the challan is marked ``adj='Y'`` once
    fully consumed). This form only ever creates fresh lines; a sibling item
    row already created by the Returnable Challan module is not reachable from
    here yet -- a separate, explicit feature (a "pull from pending challan"
    picker), not part of the field list this build was scoped against.
Date of supply / time of supply / place of supply / e-way no / e-way date /
"tax payable on reverse charge" have no column on ``bill``, so (exactly as
apps.gst_invoice does) they're kept in apps.gst_invoice.models.GstInvoiceExtra,
keyed by the same globally-unique bill_no -- not duplicated into a second table.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import connections, transaction

from apps.gst_invoice.models import GstInvoiceExtra

DIV = "SP"
BILL_TYPE = "P"
FREIGHT_CODE = "F001"
FREIGHT_GST_CODE = "F003"
GST_RATES = (0, 5, 12, 18, 28)
Q2 = Decimal("0.01")


class SpareInvoiceError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise SpareInvoiceError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _rows(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exec(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _d(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal("0")


def _date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _q2(value):
    return _d(value).quantize(Q2, ROUND_HALF_UP)


# --- numbering (shared counter with apps.gst_invoice -- see module docstring) ----------

def next_no():
    rows = _rows("SELECT gb_inv_no FROM inv_no")
    return int(_d(rows[0]["gb_inv_no"])) + 1 if rows else 1


def _allocate_no():
    with connections["legacy"].cursor() as cur:
        cur.execute("SELECT gb_inv_no FROM inv_no WITH (UPDLOCK, HOLDLOCK)")
        row = cur.fetchone()
        current = int(_d(row[0])) if row else 0
        new_no = current + 1
        cur.execute("UPDATE inv_no SET gb_inv_no = %s", [new_no])
    return str(new_no)


# --- listing ---------------------------------------------------------------------------

def list_invoices(start, end, search=""):
    # bill_no is NOT a unique key in this table on its own -- real data has many
    # rows sharing the same bill_no across different div/vou_no (mostly old div='OL'
    # history predating the div='SP' numbering this app itself allocates through
    # next_no()/_allocate_no()). Every row this returns must carry its own div and
    # vou_no, and every other lookup below (get_invoice, print_data, save_invoice's
    # modify path, delete_invoice) must be scoped by the full (bill_no, div, vou_no)
    # triple -- bill_no/bill_type alone silently matches the wrong invoice.
    search = (search or "").strip().upper()
    rows = _rows(
        "SELECT b.bill_no, b.div, b.vou_no, b.b_date, b.ca_cr, b.p_code, b.c_party, b.c_city, b.n_amount, "
        "c.cname, c.cadd3 "
        "FROM bill b LEFT JOIN cust_mst c ON c.ccode = b.p_code "
        "WHERE b.bill_type = %s AND b.b_date >= %s AND b.b_date <= %s "
        "ORDER BY b.b_date, b.bill_no",
        [BILL_TYPE, start, end],
    )
    out = []
    for r in rows:
        is_cash = (_clean(r["ca_cr"]) or "").upper() == "CA"
        name = _clean(r["c_party"]) if is_cash else _clean(r["cname"])
        city = _clean(r["c_city"]) if is_cash else _clean(r["cadd3"])
        name = name or ""
        if search and not name.upper().startswith(search):
            continue
        bill_no, div, vou_no = _clean(r["bill_no"]), _clean(r["div"]), _clean(r["vou_no"])
        out.append({
            "key": f"{bill_no}|{div}|{vou_no}", "bill_no": bill_no, "div": div, "vou_no": vou_no,
            "date": r["b_date"].isoformat() if r["b_date"] else "",
            "party": name, "city": city or "",
            "net_amount": f"{_d(r['n_amount']):.2f}",
        })
    return out


# --- GST ledger (apps.gst.GstRate) ------------------------------------------------------

def _gst_accounts():
    rows = _rows(
        "SELECT gst_rt, sl_code, sale_code, sale_cgst, sale_sgst, sali_code, sale_igst FROM gst"
    )
    return {int(_d(r["gst_rt"])): r for r in rows}


# --- part / party lookups for the Add form ----------------------------------------------

def search_items(q):
    q = (q or "").strip().upper()
    if q:
        rows = _rows(
            'SELECT icod, ides, uom, gs_rt FROM [part-mst] WHERE UPPER(icod) LIKE %s OR UPPER(ides) LIKE %s '
            "ORDER BY ides",
            [f"%{q}%", f"%{q}%"],
        )
    else:
        rows = _rows('SELECT icod, ides, uom, gs_rt FROM [part-mst] ORDER BY ides')
    return [{"code": _clean(r["icod"]), "name": _clean(r["ides"]) or "", "unit": _clean(r["uom"]) or "",
             "gst": f"{_d(r['gs_rt']):.2f}"} for r in rows[:20]]


def item_detail(code):
    rows = _rows(
        'SELECT icod, ides, uom, hs_code, gs_rt, srate, cur_stk FROM [part-mst] WHERE icod = %s',
        [(code or "").strip().upper()],
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "code": _clean(r["icod"]), "name": _clean(r["ides"]) or "", "unit": _clean(r["uom"]) or "",
        "hsn": _clean(r["hs_code"]) or "", "gst_pct": f"{_d(r['gs_rt']):.2f}", "rate": f"{_d(r['srate']):.2f}",
        "stock": f"{_d(r['cur_stk']):.0f}",
    }


def search_parties(q):
    q = (q or "").strip().upper()
    if q:
        rows = _rows(
            "SELECT ccode, cname, cadd3 FROM cust_mst WHERE UPPER(cname) LIKE %s ORDER BY cname",
            [f"%{q}%"],
        )
    else:
        rows = _rows("SELECT ccode, cname, cadd3 FROM cust_mst ORDER BY cname")
    return [{"code": _clean(r["ccode"]), "name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or ""}
            for r in rows[:20]]


def party_detail(code):
    rows = _rows(
        "SELECT ccode, cname, cadd3, gst_no, cphno, cstat FROM cust_mst WHERE ccode = %s",
        [(code or "").strip().upper()],
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "code": _clean(r["ccode"]), "name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or "",
        "gst_no": _clean(r["gst_no"]) or "", "phone": _clean(r["cphno"]) or "",
        "supply_type": _clean(r["cstat"]) or "W",
    }


# --- validation --------------------------------------------------------------------------

def _validate(payload):
    errors = {}
    is_cash = (payload.get("ca_cr") or "CR").upper() == "CA"
    party_code = (payload.get("party_code") or "").strip().upper()
    cash_name = (payload.get("cash_party_name") or "").strip()
    if is_cash:
        if not cash_name:
            errors["cash_party_name"] = "Enter the cash party name."
    else:
        if not party_code:
            errors["party_code"] = "Select the party."
        elif not _rows("SELECT ccode FROM cust_mst WHERE ccode = %s", [party_code]):
            errors["party_code"] = "Party not found."

    lines = []
    for n, row in enumerate(payload.get("items") or [], start=1):
        code = (row.get("item_code") or "").strip().upper()
        if not code:
            continue
        part = _rows('SELECT icod, hs_code, uom, gs_rt FROM [part-mst] WHERE icod = %s', [code])
        if not part:
            errors.setdefault("items", f"Row {n}: '{code}' isn't in the Part Master.")
            continue
        qty = _d(row.get("qty"))
        rate = _d(row.get("rate"))
        if qty <= 0:
            errors.setdefault("items", f"Row {n}: quantity must be greater than zero.")
            continue
        if rate < 0:
            errors.setdefault("items", f"Row {n}: rate can't be negative.")
            continue
        dis = _d(row.get("dis_pct"))
        gst_pct = int(_d(part[0]["gs_rt"]))
        if gst_pct not in GST_RATES:
            errors.setdefault("items", f"Row {n}: GST rate {gst_pct}% isn't 0/5/12/18/28.")
            continue
        amount = _q2(qty * rate * (1 - dis / 100))
        # source_chl_no/source_sno (both optional): present only on a line that came
        # from "ADD CHALLAN" -- see save_invoice(), which re-assigns that exact
        # existing imaster row (same as the legacy rpldata) instead of inserting a
        # fresh one, so the challan's own line disappears rather than being
        # duplicated. A line entered normally never carries these.
        lines.append({
            "item_code": code, "hsn_code": _clean(part[0]["hs_code"]) or "", "unit": _clean(part[0]["uom"]) or "",
            "order_no": (row.get("order_no") or "").strip(), "qty": qty, "rate": rate, "dis_pct": dis,
            "amount": amount, "gst_pct": gst_pct, "gst_amount": _q2(amount * gst_pct / 100),
            # Deselected (struck-through) on the entry screen: kept in the list and
            # saved, but excluded from totals/stock/ledger -- see save_invoice().
            "active": row.get("active", True) is not False,
            "particular": (row.get("particular") or "").strip()[:100],
            "source_chl_no": (row.get("source_chl_no") or "").strip() or None,
            "source_sno": row.get("source_sno"),
        })
    if not lines and "items" not in errors:
        errors["items"] = "Add at least one item."
    if errors:
        raise SpareInvoiceError("Fix the highlighted fields.", errors)
    return is_cash, party_code, cash_name, lines


# --- totals (mirrors the legacy "caltotal" routine, same as apps.gst_invoice) -----------

def compute_totals(lines, supply_type, freight, freight_gst_pct, adjustments):
    interstate = (supply_type or "").upper() == "I"
    buckets = {r: {"taxable": Decimal("0")} for r in GST_RATES}
    for l in lines:
        buckets[l["gst_pct"]]["taxable"] += l["amount"]

    amount = sum((l["amount"] for l in lines), Decimal("0"))
    gst_total = Decimal("0")
    gst_detail = {}
    for rate in GST_RATES:
        taxable = buckets[rate]["taxable"]
        if rate == 0 or taxable == 0:
            continue
        if interstate:
            igst = _q2(taxable * rate / 100)
            gst_detail[rate] = {"igst_rt": Decimal(rate), "igst_amt": igst}
            gst_total += igst
        else:
            half = Decimal(rate) / 2
            cgst = _q2(taxable * half / 100)
            sgst = _q2(taxable * half / 100)
            gst_detail[rate] = {"cgst_rt": half, "cgst_amt": cgst, "sgst_rt": half, "sgst_amt": sgst}
            gst_total += cgst + sgst

    freight = _q2(freight)
    freight_gst = _q2(freight * _d(freight_gst_pct) / 100)
    net = amount + gst_total + freight + freight_gst
    for adj in adjustments:
        net += adj["amount"] if adj["sign"] == "A" else -adj["amount"]
    net_rounded = net.to_integral_value(rounding=ROUND_HALF_UP)
    diff = net - net_rounded

    return {
        "taxable_by_rate": {r: buckets[r]["taxable"] for r in GST_RATES},
        "gst_detail": gst_detail, "amount": amount, "gst_total": gst_total,
        "freight": freight, "freight_gst": freight_gst, "net": net,
        "net_rounded": net_rounded, "diff": diff, "interstate": interstate,
    }


# --- stock / order reconciliation (apps.parts.Part / ord_dat) ---------------------------

def _adjust_stock(item_code, qty_delta):
    """``qty_delta`` > 0 restores stock (delete), < 0 consumes it (save) -- matches
    the real VFP ``repl cur_stk with cur_stk+(imaster->qty)`` (delete) /
    ``repl cur_stk with cur_stk-val(...)`` (save)."""
    _exec('UPDATE [part-mst] SET cur_stk = COALESCE(cur_stk, 0) + %s WHERE icod = %s', [qty_delta, item_code])


def _adjust_order(party_code, order_no, item_code, qty_delta):
    """Mirrors the VFP ``repl qty_iss with qty_iss +/- imaster->qty`` against
    ``ord_dat``, matched the same way the real form does: party + order no + item.
    Silently does nothing if no matching pending-order row is found (same as the
    VFP ``if found()`` guard) -- ORDER NO on a line is optional free text here."""
    if not order_no:
        return
    _exec(
        "UPDATE ord_dat SET qty_iss = COALESCE(qty_iss, 0) + %s "
        "WHERE p_code = %s AND ord_no = %s AND i_code = %s",
        [qty_delta, party_code, order_no, item_code],
    )


# --- save / delete -----------------------------------------------------------------------

def _next_vno(bill_date):
    with connections["legacy"].cursor() as cur:
        cur.execute("SELECT svvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [bill_date])
        row = cur.fetchone()
        if row:
            current = int(_d(row[0])) + 1
            cur.execute("UPDATE vno SET svvno = %s WHERE date = %s", [current, bill_date])
        else:
            current = 1
            cur.execute("INSERT INTO vno (date, svvno) VALUES (%s, %s)", [bill_date, current])
    return current


def _reverse_ledger(bill_no, div):
    _exec("DELETE FROM trans WHERE tnar1 = %s AND div = %s AND bill_type = %s",
          [f"BILL NO.{BILL_TYPE}-{bill_no}", div, BILL_TYPE])


def _post_ledger(bill_no, bill_date, vno, is_cash, party_code, totals, accounts, adjustments, username):
    narration = f"BILL NO.{BILL_TYPE}-{bill_no}"

    def post(tdbcr, tcode, amount, tccode=""):
        if amount == 0:
            return
        _exec(
            "INSERT INTO trans (ttype, tdoc, tdate, tcode, tccode, tdbcr, tnar1, tamt, div, gbill_no, bill_type, uname) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ["SV", vno, bill_date, tcode, tccode, tdbcr, narration, amount, DIV, bill_no, BILL_TYPE, username[:10]],
        )

    for rate, detail in totals["gst_detail"].items():
        acc = accounts.get(rate) or {}
        taxable = totals["taxable_by_rate"][rate]
        if "igst_amt" in detail:
            post("C", _clean(acc.get("sali_code")), taxable)
            post("C", _clean(acc.get("sale_igst")), detail["igst_amt"])
        else:
            post("C", _clean(acc.get("sale_code")), taxable)
            post("C", _clean(acc.get("sale_cgst")), detail["cgst_amt"])
            post("C", _clean(acc.get("sale_sgst")), detail["sgst_amt"])
    taxfree = totals["taxable_by_rate"].get(0, Decimal("0"))
    if taxfree:
        post("C", _clean((accounts.get(0) or {}).get("sl_code")), taxfree)

    for adj in adjustments:
        if adj["amount"] == 0 or not adj["code"]:
            continue
        post("C" if adj["sign"] == "A" else "D", adj["code"], adj["amount"])

    if totals["freight"] != 0:
        post("C", FREIGHT_CODE, totals["freight"])
    if totals["freight_gst"] != 0:
        post("C", FREIGHT_GST_CODE, totals["freight_gst"])

    if is_cash:
        post("D", "", totals["net_rounded"])
    else:
        post("D", party_code, totals["net_rounded"], tccode=party_code)


def get_invoice(bill_no, div=None, vou_no=None):
    """div/vou_no disambiguate which physical row to open when bill_no collides
    across rows (see list_invoices' docstring note) -- callers that already have
    a specific row (from list_invoices) must always pass both. Left optional only
    so old callers/tests without a specific row still get the previous (first-match)
    behaviour rather than breaking outright."""
    where = ["b.bill_no = %s", "b.bill_type = %s"]
    params = [bill_no, BILL_TYPE]
    if div is not None:
        where.append("b.div = %s")
        params.append(div)
    if vou_no is not None:
        where.append("b.vou_no = %s")
        params.append(vou_no)
    rows = _rows(
        "SELECT b.*, c.cname, c.cadd1, c.cadd2, c.cadd3, c.gst_no AS p_gst_no, c.cphno, c.gscode, c.stname "
        "FROM bill b LEFT JOIN cust_mst c ON c.ccode = b.p_code "
        "WHERE " + " AND ".join(where), params,
    )
    if not rows:
        return None
    h = rows[0]
    is_cash = (_clean(h["ca_cr"]) or "").upper() == "CA"
    # imaster has no vou_no column -- div is as precise as items can be scoped,
    # which matches reality: duplicate bill_no rows sharing one div never both
    # carry item rows in practice (the older ones are header-only history).
    items_where = ["m.bill_no = %s", "m.bill_type = %s", "m.stts IN ('S', 'X')"]
    items_params = [bill_no, BILL_TYPE]
    if div is not None:
        items_where.append("m.div = %s")
        items_params.append(div)
    items = _rows(
        "SELECT m.i_code, m.order_no, m.qty, m.rate, m.amount, m.gst, m.gst_amt, m.hs_code, m.unit, m.particular, "
        "m.stts, p.ides AS i_name FROM imaster m LEFT JOIN [part-mst] p ON p.icod = m.i_code "
        "WHERE " + " AND ".join(items_where) + " ORDER BY m.sno", items_params,
    )
    extra = GstInvoiceExtra.objects.filter(bill_no=bill_no).first()
    adjustments = []
    for i in (1, 2):
        code = _clean(h.get(f"adj_code{i}"))
        amt = _d(h.get(f"adj_amt{i}"))
        if code and amt:
            ledger = _rows("SELECT gdesc FROM gled_mst WHERE gcode = %s", [code])
            adjustments.append({
                "sign": _clean(h.get(f"adj{i}")) or "A", "code": code,
                "name": _clean(ledger[0]["gdesc"]) if ledger else code,
                "amount": f"{amt:.2f}",
            })
    return {
        "bill_no": _clean(h["bill_no"]), "div": _clean(h["div"]), "vou_no": _clean(h["vou_no"]),
        "date": h["b_date"].isoformat() if h["b_date"] else "",
        "ca_cr": _clean(h["ca_cr"]) or "CR", "chk_order": _clean(h["chk_ord"]) or "N",
        "party_code": "" if is_cash else _clean(h["p_code"]),
        "party_name": "" if is_cash else _clean(h["cname"]) or "",
        "party_address": "" if is_cash else ", ".join(
            p for p in [_clean(h["cadd1"]), _clean(h["cadd2"])] if p
        ),
        "city": "" if is_cash else _clean(h["cadd3"]) or "",
        "party_state_code": "" if is_cash else _clean(h["gscode"]) or "",
        "party_state_name": "" if is_cash else _clean(h["stname"]) or "",
        "cash_party_name": _clean(h["c_party"]) if is_cash else "",
        "cash_party_city": _clean(h["c_city"]) if is_cash else "",
        "gst_no": _clean(h["p_gst_no"]) or "", "phone": _clean(h["phno"]) or "",
        "supply_type": _clean(h["cstat"]) or "W",
        "consignee_name": _clean(h["cname"]) or "", "consignee_address": _clean(h["cadd"]) or "",
        "order_no": _clean(h["ord_no1"]) or "", "order_date": h["ord_dt1"].isoformat() if h["ord_dt1"] else "",
        "gr_no": _clean(h["gr_no"]) or "", "gr_date": h["gr_dt"].isoformat() if h["gr_dt"] else "",
        "transport": _clean(h["trans"]) or "", "remarks": _clean(h["remk"]) or "",
        "vehicle_no": _clean(h["lr_no"]) or "",
        "freight": f"{_d(h['fr_amt']):.2f}", "freight_rate": f"{_d(h['fr_rt']):.2f}",
        "freight_gst": f"{_d(h['fr_amt1']):.2f}",
        "amount": f"{_d(h['amount']):.2f}", "gst_amount": f"{_d(h['gst_amt']):.2f}",
        "due_balance": f"{_d(h['cur_bal']):.2f}",
        "net_amount": f"{_d(h['n_amount']):.2f}",
        "adjustments": adjustments,
        "items": [{
            "item_code": _clean(r["i_code"]), "item_name": _clean(r["i_name"]) or "",
            "hsn_code": _clean(r["hs_code"]) or "", "unit": _clean(r["unit"]) or "",
            "order_no": _clean(r["order_no"]) or "", "qty": f"{_d(r['qty']):.3f}",
            "rate": f"{_d(r['rate']):.2f}", "gst_pct": f"{_d(r['gst']):.2f}",
            "amount": f"{_d(r['amount']):.2f}", "gst_amt": _d(r["gst_amt"]),
            "active": _clean(r["stts"]) != "X",
            "particular": _clean(r["particular"]) or "",
        } for r in items],
        "date_of_supply": extra.date_of_supply.isoformat() if extra and extra.date_of_supply else "",
        "time_of_supply": extra.time_of_supply if extra else "",
        "place_of_supply": extra.place_of_supply if extra else "",
        "eway_no": extra.eway_no if extra else "",
        "eway_date": extra.eway_date.isoformat() if extra and extra.eway_date else "",
        "reverse_charge": extra.reverse_charge if extra else False,
    }


# --- print -------------------------------------------------------------------------------

def print_data(bill_no, div=None, vou_no=None):
    """Tax Invoice print view: same get_invoice() data, plus each line split into its
    own CGST+SGST (within state) or IGST (interstate) rate/amount, matching the
    legacy VFP report ``gpinvex1`` (the same GST tax-invoice layout GST Billing's own
    bill_type='G' print used, reused here filtered to this screen's own 'P' rows)."""
    data = get_invoice(bill_no, div, vou_no)
    if not data:
        return None
    interstate = (data["supply_type"] or "W").upper() == "I"
    cgst_total = sgst_total = igst_total = Decimal("0")
    cgst_by_rate, sgst_by_rate, igst_by_rate = {}, {}, {}
    for l in data["items"]:
        l.pop("gst_amt", None)  # the stored per-line column isn't reliable on older rows -- recompute below
        l["qty"] = f"{_d(l['qty']):.0f}"  # printed Qty is whole units (matches the legacy Tax Invoice layout)
        if not l["active"]:
            l.update(cgst_rate="0.00", cgst_amt="0.00", sgst_rate="0.00", sgst_amt="0.00",
                      igst_rate="0.00", igst_amt="0.00")
            continue
        gst_pct = _d(l["gst_pct"])
        amount = _d(l["amount"])
        gst_amt = _q2(amount * gst_pct / 100)
        if interstate:
            l.update(cgst_rate="0.00", cgst_amt="0.00", sgst_rate="0.00", sgst_amt="0.00",
                      igst_rate=f"{gst_pct:.2f}", igst_amt=f"{gst_amt:.2f}")
            igst_total += gst_amt
            igst_by_rate[gst_pct] = igst_by_rate.get(gst_pct, Decimal("0")) + gst_amt
        else:
            half_rate, half_amt = gst_pct / 2, _q2(gst_amt / 2)
            l.update(cgst_rate=f"{half_rate:.2f}", cgst_amt=f"{half_amt:.2f}",
                      sgst_rate=f"{half_rate:.2f}", sgst_amt=f"{half_amt:.2f}",
                      igst_rate="0.00", igst_amt="0.00")
            cgst_total += half_amt
            sgst_total += half_amt
            cgst_by_rate[gst_pct] = cgst_by_rate.get(gst_pct, Decimal("0")) + half_amt
            sgst_by_rate[gst_pct] = sgst_by_rate.get(gst_pct, Decimal("0")) + half_amt
    data["cgst_total"] = f"{cgst_total:.2f}"
    data["sgst_total"] = f"{sgst_total:.2f}"
    data["igst_total"] = f"{igst_total:.2f}"
    data["interstate"] = interstate
    # Interstate sales show one IGST line per rate; within-state sales show CGST
    # then SGST (each at half the GST rate) per rate -- never a generic "Sale" line.
    rate_breakdown = []
    if interstate:
        for rate in sorted(igst_by_rate):
            if rate > 0:
                rate_breakdown.append({"label": "IGST", "rate": f"{rate:.2f}", "amount": f"{igst_by_rate[rate]:.2f}"})
    else:
        for rate in sorted(cgst_by_rate):
            if rate <= 0:
                continue
            half_rate = rate / 2
            rate_breakdown.append({"label": "CGST", "rate": f"{half_rate:.2f}", "amount": f"{cgst_by_rate[rate]:.2f}"})
            rate_breakdown.append({"label": "SGST", "rate": f"{half_rate:.2f}", "amount": f"{sgst_by_rate[rate]:.2f}"})
    data["rate_breakdown"] = rate_breakdown
    return data


def _delete_legacy(bill_no, div, vou_no):
    items = _rows("SELECT i_code, order_no, qty, stts FROM imaster WHERE bill_no = %s AND bill_type = %s AND div = %s",
                   [bill_no, BILL_TYPE, div])
    party = _rows("SELECT p_code FROM bill WHERE bill_no = %s AND bill_type = %s AND div = %s AND vou_no = %s",
                  [bill_no, BILL_TYPE, div, vou_no])
    party_code = _clean(party[0]["p_code"]) if party else ""
    for it in items:
        if _clean(it["stts"]) == "X":  # deselected -- never touched stock/order, nothing to reverse
            continue
        code = _clean(it["i_code"])
        qty = _d(it["qty"])
        _adjust_stock(code, qty)
        _adjust_order(party_code, _clean(it["order_no"]), code, -qty)
    _exec("DELETE FROM imaster WHERE bill_no = %s AND bill_type = %s AND div = %s", [bill_no, BILL_TYPE, div])
    _exec("DELETE FROM bill WHERE bill_no = %s AND bill_type = %s AND div = %s AND vou_no = %s",
          [bill_no, BILL_TYPE, div, vou_no])
    _reverse_ledger(bill_no, div)
    GstInvoiceExtra.objects.filter(bill_no=bill_no).delete()


def save_invoice(payload, key=None, key_div=None, key_vou_no=None, username=""):
    _require_writes()
    bill_date = _date(payload.get("date"))
    if not bill_date:
        raise SpareInvoiceError("Fix the highlighted fields.", {"date": "Date is required."})
    is_cash, party_code, cash_party_name, lines = _validate(payload)
    supply_type = (payload.get("supply_type") or "W").upper()
    freight = _d(payload.get("freight"))
    freight_gst_pct = _d(payload.get("freight_gst_pct"))
    adjustments = []
    for a in payload.get("adjustments") or []:
        code = (a.get("code") or "").strip().upper()
        amt = _q2(a.get("amount"))
        sign = (a.get("sign") or "A").upper()
        if code and amt:
            adjustments.append({"code": code, "amount": amt, "sign": sign})
    accounts = _gst_accounts()
    active_lines = [l for l in lines if l["active"]]
    # Deselected lines are excluded from totals/GST/ledger -- same compute_totals()
    # as before, just fed only the active subset.
    totals = compute_totals(active_lines, supply_type, freight, freight_gst_pct, adjustments)

    with transaction.atomic(using="legacy"):
        if key:
            # bill_no alone doesn't identify one row (see list_invoices' docstring
            # note) -- key_div/key_vou_no must pin down the exact row being
            # modified, or this would silently overwrite every other invoice that
            # happens to share this bill_no too.
            bill_no = key
            if not key_div or not key_vou_no:
                raise SpareInvoiceError("This Spare Part invoice no longer exists.")
            if not _rows("SELECT bill_no FROM bill WHERE bill_no = %s AND bill_type = %s AND div = %s AND vou_no = %s",
                         [bill_no, BILL_TYPE, key_div, key_vou_no]):
                raise SpareInvoiceError("This Spare Part invoice no longer exists.")
            old_items = _rows("SELECT i_code, order_no, qty, stts FROM imaster WHERE bill_no = %s AND bill_type = %s AND div = %s",
                               [bill_no, BILL_TYPE, key_div])
            old_party = _rows("SELECT p_code FROM bill WHERE bill_no = %s AND bill_type = %s AND div = %s AND vou_no = %s",
                              [bill_no, BILL_TYPE, key_div, key_vou_no])
            old_party_code = _clean(old_party[0]["p_code"]) if old_party else ""
            for it in old_items:
                # Only reverse stock/order for lines that were actually active (stts
                # 'S') before -- a deselected line never touched stock/order in the
                # first place, so there's nothing to credit back for it.
                if _clean(it["stts"]) == "X":
                    continue
                code = _clean(it["i_code"])
                qty = _d(it["qty"])
                _adjust_stock(code, qty)
                _adjust_order(old_party_code, _clean(it["order_no"]), code, -qty)
            _exec("DELETE FROM imaster WHERE bill_no = %s AND bill_type = %s AND div = %s", [bill_no, BILL_TYPE, key_div])
            _reverse_ledger(bill_no, key_div)
            vno = _next_vno(bill_date)
        else:
            bill_no = _allocate_no()
            # Scoped by div too -- bill_no collides with old div='OL' historical
            # rows for this same bill_type (confirmed real data, see this
            # module's own docstring), a different division and not a real
            # conflict with the row this save is about to create (always
            # div='SP'). An unscoped check here false-positived on every single
            # Add once the counter reached a number an old OL row already used,
            # blocking new invoices outright.
            if _rows("SELECT bill_no FROM bill WHERE bill_no = %s AND bill_type = %s AND div = %s", [bill_no, BILL_TYPE, DIV]):
                raise SpareInvoiceError("This bill no. already exists.")
            vno = _next_vno(bill_date)

        consumed_chl_nos = set()
        for n, l in enumerate(lines, start=1):
            # stts: 'S' (saved/active, the only value the legacy form itself ever
            # writes) or 'X' (deselected on the web entry screen -- a new, web-only
            # value; never written by the legacy app, so it can't collide with any
            # of its own semantics, e.g. challan-sourced pending rows).
            stts = "S" if l["active"] else "X"
            row_values = [bill_no, DIV, bill_date, party_code, n, l["hsn_code"], l["unit"], l["amount"],
                          l["gst_pct"], l["gst_amount"], BILL_TYPE, supply_type, l["order_no"], l["qty"],
                          l["rate"], stts, username[:10], l["particular"]]
            if l["source_chl_no"]:
                # ADD CHALLAN import: re-assign the challan's own existing imaster
                # row (matching the real VFP rpldata -- items already in imaster
                # with a chl_no and no bill_no get re-assigned, not duplicated)
                # instead of inserting a fresh one. The WHERE clause re-checks
                # bill_no is still empty at save time -- not just when the picker
                # was opened -- so two invoices racing to import the same challan
                # line can't both succeed.
                with connections["legacy"].cursor() as cur:
                    cur.execute(
                        "UPDATE imaster SET bill_no=%s, div=%s, date=%s, p_code=%s, sno=%s, hs_code=%s, unit=%s, "
                        "amount=%s, gst=%s, gst_amt=%s, bill_type=%s, cstat=%s, order_no=%s, qty=%s, rate=%s, "
                        "stts=%s, uname=%s, particular=%s "
                        "WHERE chl_no=%s AND sno=%s AND i_code=%s AND stts='S' AND (bill_no IS NULL OR bill_no='')",
                        row_values + [l["source_chl_no"], l["source_sno"], l["item_code"]],
                    )
                    if cur.rowcount == 0:
                        raise SpareInvoiceError(
                            f"Challan {l['source_chl_no']}'s '{l['item_code']}' line was already billed "
                            "on another invoice -- remove it and save again.",
                            {"items": "One of the imported challan lines is no longer available."},
                        )
                consumed_chl_nos.add(l["source_chl_no"])
            else:
                _exec(
                    "INSERT INTO imaster (bill_no, div, date, p_code, sno, i_code, hs_code, unit, amount, "
                    "gst, gst_amt, bill_type, cstat, order_no, qty, rate, stts, uname, particular) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    row_values[:5] + [l["item_code"]] + row_values[5:],
                )
            if l["active"]:
                _adjust_stock(l["item_code"], -l["qty"])
                _adjust_order(party_code, l["order_no"], l["item_code"], l["qty"])

        if consumed_chl_nos:
            from apps.returnable_challan.services import mark_consumed_if_fully_billed
            for chl_no in consumed_chl_nos:
                mark_consumed_if_fully_billed(chl_no)

        gst_cols = {}
        for rate, detail in totals["gst_detail"].items():
            if "igst_amt" in detail:
                gst_cols[f"ig_rt{rate}"] = detail["igst_rt"]
                gst_cols[f"ig_amt{rate}"] = detail["igst_amt"]
            else:
                gst_cols[f"cg_rt{rate}"] = detail["cgst_rt"]
                gst_cols[f"cg_amt{rate}"] = detail["cgst_amt"]
                gst_cols[f"sg_rt{rate}"] = detail["sgst_rt"]
                gst_cols[f"sg_amt{rate}"] = detail["sgst_amt"]
        amt_cols = {
            "amt_tf": totals["taxable_by_rate"][0], "amt5": totals["taxable_by_rate"][5],
            "amt12": totals["taxable_by_rate"][12], "amt18": totals["taxable_by_rate"][18],
            "amt28": totals["taxable_by_rate"][28],
        }
        adj_cols = {}
        for i in range(1, 3):
            a = adjustments[i - 1] if i <= len(adjustments) else None
            adj_cols[f"adj{i}"] = a["sign"] if a else ""
            adj_cols[f"adj_code{i}"] = a["code"] if a else ""
            adj_cols[f"adj_amt{i}"] = a["amount"] if a else Decimal("0")

        all_cols = {
            "div": DIV, "b_date": bill_date, "p_code": party_code if not is_cash else "",
            "ca_cr": "CA" if is_cash else "CR", "chk_ord": (payload.get("chk_order") or "N").upper(),
            "c_party": cash_party_name if is_cash else "", "c_city": (payload.get("cash_party_city") or "").strip(),
            "gst_no": (payload.get("gst_no") or "").strip(), "phno": (payload.get("phone") or "").strip(),
            "cstat": supply_type, "cname": (payload.get("consignee_name") or "").strip(),
            "cadd": (payload.get("consignee_address") or "").strip(),
            "ord_no1": (payload.get("order_no") or "").strip(), "ord_dt1": _date(payload.get("order_date")),
            "gr_no": (payload.get("gr_no") or "").strip(), "gr_dt": _date(payload.get("gr_date")),
            "trans": (payload.get("transport") or "").strip(), "remk": (payload.get("remarks") or "")[:40],
            "lr_no": (payload.get("vehicle_no") or "").strip(),
            "amount": totals["amount"], "gst_amt": totals["gst_total"], "n_amount": totals["net_rounded"],
            "diff_amt": totals["diff"], "pmt_rcd": "N", "fr_rt": freight_gst_pct, "fr_amt": freight,
            "fr_amt1": totals["freight_gst"], "vou_no": str(vno), "bill_type": BILL_TYPE,
            "uname": username[:10],
            **amt_cols, **gst_cols, **adj_cols,
        }
        cols = list(all_cols.keys())
        placeholders = ",".join(["%s"] * len(cols))
        values = [all_cols[c] for c in cols]
        if key:
            set_clause = ",".join(f"{c} = %s" for c in cols)
            _exec(f"UPDATE bill SET {set_clause} WHERE bill_no = %s AND bill_type = %s AND div = %s AND vou_no = %s",
                  values + [bill_no, BILL_TYPE, key_div, key_vou_no])
        else:
            _exec(
                f"INSERT INTO bill (bill_no, {', '.join(cols)}) VALUES (%s, {placeholders})",
                [bill_no] + values,
            )

        _post_ledger(bill_no, bill_date, vno, is_cash, party_code, totals, accounts, adjustments, username)

        GstInvoiceExtra.objects.update_or_create(
            bill_no=bill_no,
            defaults={
                "date_of_supply": _date(payload.get("date_of_supply")),
                "time_of_supply": (payload.get("time_of_supply") or "")[:10],
                "place_of_supply": (payload.get("place_of_supply") or "")[:40],
                "eway_no": (payload.get("eway_no") or "")[:20],
                "eway_date": _date(payload.get("eway_date")),
                "reverse_charge": bool(payload.get("reverse_charge")),
            },
        )

    return {"bill_no": bill_no}


def delete_invoice(bill_no, div, vou_no):
    _require_writes()
    if not div or not vou_no:
        raise SpareInvoiceError("This Spare Part invoice no longer exists.")
    with transaction.atomic(using="legacy"):
        if not _rows("SELECT bill_no FROM bill WHERE bill_no = %s AND bill_type = %s AND div = %s AND vou_no = %s",
                     [bill_no, BILL_TYPE, div, vou_no]):
            raise SpareInvoiceError("This Spare Part invoice no longer exists.")
        _delete_legacy(bill_no, div, vou_no)
        row = _rows("SELECT gb_inv_no FROM inv_no")
        if row and str(int(_d(row[0]["gb_inv_no"]))) == str(bill_no):
            _exec("UPDATE inv_no SET gb_inv_no = %s", [int(bill_no) - 1])

"""
GST Invoice (old VFP form "INVOICE" / file gstbill5.SCX, list form "GST INVOICE").

Header lives in the existing ``bill`` table (``bill_type = 'G'``), same physical
table apps.outstanding.models.Bill and apps.debit_note map different column
subsets of. Line items live in ``i_master`` (a different table from the
``imaster`` MRN/Issue Slip/Debit Note share). Both are addressed with raw SQL
(``apps.sale_order.services`` already does this for ``order1``/``ord_mst``
rather than adding more unmanaged models) because of how many columns the
real rows carry.

Division code ("SP") and the rounding-difference ledger code ("D001") are the
two VFP globals (``pdv``, ``pdiffcode``) the legacy save routine reads from
outside any data table. "SP" was given directly by the project owner; "D001"
was found, not guessed, by reading the real ``trans`` rows already posted for
existing GST bills -- every one of them carries a small leftover balancing
line under ``tcode = 'D001'``, and ``gled_mst`` names that code "DIFFERENCE
ACCOUNT" (apps.gl.models.Ledger).

Deliberately NOT implemented (would mean guessing legacy behaviour this
project's own convention refuses to guess):
  * Linking a line to a pending Sale Order (``order1``/``torder1`` stock
    reconciliation) -- "CHECK ORDER Y/N" is saved as a flag only.
  * Decrementing any stock balance on save -- no existing module in this
    project reduces finished-item stock on a sale; inventing that rule here
    would risk double-counting against whatever process already does it in
    the legacy app (same reasoning as apps.issue_slip.services).
  * WhatsApp send and the PRINT button -- no printed layout was supplied.
Vehicle No / Date of Supply / Time of Supply / Place of Supply / E-Way No /
E-Way Date / "tax payable on reverse charge" have no column on ``bill`` in
the supplied save routine, so they're kept locally in GstInvoiceExtra instead
(same convention as apps.debit_note.models.DebitNote.place_of_supply).
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import connections, transaction

from .models import GstInvoiceExtra

DIV = "SP"
DIFF_LEDGER_CODE = "D001"
BILL_TYPE = "G"
GST_RATES = (0, 5, 12, 18, 28)
Q2 = Decimal("0.01")


class GstInvoiceError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise GstInvoiceError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


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


# --- numbering -----------------------------------------------------------------------

def next_no():
    rows = _rows("SELECT gb_inv_no FROM inv_no")
    return int(_d(rows[0]["gb_inv_no"])) + 1 if rows else 1


def _allocate_no():
    """The real, locked allocation (called inside save_invoice()'s own transaction).
    A plain SELECT then UPDATE is racy under SQL Server's default READ COMMITTED
    isolation -- two concurrent saves could both read the same gb_inv_no before
    either writes it back. `WITH (UPDLOCK, HOLDLOCK)` (SQL Server's equivalent of
    `SELECT ... FOR UPDATE`) holds this row locked until the transaction commits, so
    a second concurrent save blocks here until the first's UPDATE commits."""
    with connections["legacy"].cursor() as cur:
        cur.execute("SELECT gb_inv_no FROM inv_no WITH (UPDLOCK, HOLDLOCK)")
        row = cur.fetchone()
        current = int(_d(row[0])) if row else 0
        new_no = current + 1
        cur.execute("UPDATE inv_no SET gb_inv_no = %s", [new_no])
    return str(new_no)


# --- listing ---------------------------------------------------------------------------

def list_invoices(start, end, search=""):
    search = (search or "").strip().upper()
    rows = _rows(
        "SELECT b.bill_no, b.b_date, b.ca_cr, b.p_code, b.c_party, b.c_city, b.n_amount, "
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
        out.append({
            "key": _clean(r["bill_no"]), "bill_no": _clean(r["bill_no"]),
            "date": r["b_date"].isoformat() if r["b_date"] else "",
            "party": name, "city": city or "",
            "net_amount": f"{_d(r['n_amount']):.2f}",
        })
    return out


# --- GST ledger (apps.gst.GstRate -- real sale ledger codes per rate bracket) ----------

def _gst_accounts():
    rows = _rows(
        "SELECT gst_rt, sl_code, sale_code, sale_cgst, sale_sgst, sali_code, sale_igst FROM gst"
    )
    return {int(_d(r["gst_rt"])): r for r in rows}


# --- item / party lookups for the Add form ---------------------------------------------

def search_items(q):
    q = (q or "").strip().upper()
    if q:
        rows = _rows(
            "SELECT i_code, i_name, unit, gs_rt FROM item WHERE UPPER(i_code) LIKE %s OR UPPER(i_name) LIKE %s "
            "ORDER BY i_name",
            [f"%{q}%", f"%{q}%"],
        )
    else:
        rows = _rows("SELECT i_code, i_name, unit, gs_rt FROM item ORDER BY i_name")
    return [{"code": _clean(r["i_code"]), "name": _clean(r["i_name"]) or "", "unit": _clean(r["unit"]) or "",
             "gst": f"{_d(r['gs_rt']):.2f}"} for r in rows[:20]]


def item_detail(code):
    rows = _rows("SELECT i_code, i_name, unit, hs_code, gs_rt, rate FROM item WHERE i_code = %s",
                 [(code or "").strip().upper()])
    if not rows:
        return None
    r = rows[0]
    return {
        "code": _clean(r["i_code"]), "name": _clean(r["i_name"]) or "", "unit": _clean(r["unit"]) or "",
        "hsn": _clean(r["hs_code"]) or "", "gst_pct": f"{_d(r['gs_rt']):.2f}", "rate": f"{_d(r['rate']):.2f}",
    }


def search_ledgers(q):
    q = (q or "").strip().upper()
    if q:
        rows = _rows(
            "SELECT gcode, gdesc FROM gled_mst WHERE UPPER(gcode) LIKE %s OR UPPER(gdesc) LIKE %s ORDER BY gdesc",
            [f"%{q}%", f"%{q}%"],
        )
    else:
        rows = _rows("SELECT gcode, gdesc FROM gled_mst ORDER BY gdesc")
    return [{"code": _clean(r["gcode"]), "name": _clean(r["gdesc"]) or ""} for r in rows[:20]]


def search_parties(q):
    """Party lookup for the Add form -- Sundry Debtors only (settings.PARTY_DEBTOR_CODE
    / "S001"); Sundry Creditors (vendors, "S002") are a purchase-side concept and
    should never show up when billing a customer."""
    q = (q or "").strip().upper()
    if q:
        rows = _rows(
            "SELECT ccode, cname, cadd3 FROM cust_mst WHERE code = %s AND UPPER(cname) LIKE %s ORDER BY cname",
            [settings.PARTY_DEBTOR_CODE, f"%{q}%"],
        )
    else:
        rows = _rows("SELECT ccode, cname, cadd3 FROM cust_mst WHERE code = %s ORDER BY cname",
                      [settings.PARTY_DEBTOR_CODE])
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

    if not (payload.get("consignee_name") or "").strip():
        errors["consignee_name"] = "Consignee name is required."
    if not (payload.get("consignee_address") or "").strip():
        errors["consignee_address"] = "Consignee address is required."

    lines = []
    for n, row in enumerate(payload.get("items") or [], start=1):
        code = (row.get("item_code") or "").strip().upper()
        if not code:
            continue
        item = _rows("SELECT i_code, hs_code, unit, gs_rt FROM item WHERE i_code = %s", [code])
        if not item:
            errors.setdefault("items", f"Row {n}: '{code}' isn't in the Item Master.")
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
        gst_pct = int(_d(item[0]["gs_rt"]))
        if gst_pct not in GST_RATES:
            errors.setdefault("items", f"Row {n}: GST rate {gst_pct}% isn't 0/5/12/18/28.")
            continue
        amount = _q2(qty * rate * (1 - dis / 100))
        lines.append({
            "item_code": code, "hsn_code": _clean(item[0]["hs_code"]) or "", "unit": _clean(item[0]["unit"]) or "",
            "order_no": (row.get("order_no") or "").strip(), "qty": qty, "rate": rate, "dis_pct": dis,
            "amount": amount, "gst_pct": gst_pct, "gst_amount": _q2(amount * gst_pct / 100),
        })
    if not lines and "items" not in errors:
        errors["items"] = "Add at least one item."
    if errors:
        raise GstInvoiceError("Fix the highlighted fields.", errors)
    return is_cash, party_code, cash_name, lines


# --- totals (mirrors the legacy "caltotal" routine) -------------------------------------

def compute_totals(lines, supply_type, freight, freight_gst_pct, adjustments):
    """Buckets each line's taxable value by GST rate, splits the tax into
    CGST+SGST (within state) or IGST (interstate) per ``supply_type`` (cust_mst.cstat,
    'I' = interstate), exactly like the legacy caltotal procedure."""
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


# --- save / delete -----------------------------------------------------------------------

def _next_vno(bill_date):
    """Locked the same way as _allocate_no() above -- two concurrent saves on the
    same date must not get the same voucher number. The one residual gap (two
    concurrent *first* saves of a brand-new date racing on the INSERT below, since
    UPDLOCK/HOLDLOCK locks nothing when no row exists yet to lock) is far narrower
    than the plain read-then-write this replaces, and matches what the legacy app
    itself risks for a day's first voucher."""
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


def _reverse_ledger(bill_no):
    _exec("DELETE FROM trans WHERE tnar1 = %s", [f"BILL NO.{BILL_TYPE}-{bill_no}"])


def _post_ledger(bill_no, bill_date, vno, is_cash, party_code, cash_party_name, totals, accounts,
                 adjustments, freight_code, freight_gst_code, username):
    narration = f"BILL NO.{BILL_TYPE}-{bill_no}"

    def post(tdbcr, tcode, amount, tccode=""):
        if amount == 0:
            return
        _exec(
            "INSERT INTO trans (ttype, tdoc, tdate, tcode, tccode, tdbcr, tnar1, tamt, div, uname) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ["SV", vno, bill_date, tcode, tccode, tdbcr, narration, amount, DIV, username[:10]],
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
        post("C", freight_code, totals["freight"])
    if totals["freight_gst"] != 0:
        post("C", freight_gst_code, totals["freight_gst"])

    if totals["diff"] != 0:
        post("D" if totals["diff"] > 0 else "C", DIFF_LEDGER_CODE, abs(totals["diff"]))

    if is_cash:
        post("D", "", totals["net_rounded"])
    else:
        post("D", party_code, totals["net_rounded"], tccode=party_code)


def get_invoice(bill_no):
    rows = _rows(
        "SELECT b.*, c.cname, c.cadd1, c.cadd2, c.cadd3, c.gst_no AS p_gst_no, c.cphno, c.gscode, c.stname, "
        "c.pin AS p_pin, c.ctrp AS p_transport "
        "FROM bill b LEFT JOIN cust_mst c ON c.ccode = b.p_code "
        "WHERE b.bill_no = %s AND b.bill_type = %s", [bill_no, BILL_TYPE],
    )
    if not rows:
        return None
    h = rows[0]
    is_cash = (_clean(h["ca_cr"]) or "").upper() == "CA"
    items = _rows(
        "SELECT m.i_code, m.order_no, m.qty, m.rate, m.amount, m.gst, m.gst_amt, m.hs_code, m.unit, "
        "i.i_name FROM i_master m LEFT JOIN item i ON i.i_code = m.i_code "
        "WHERE m.bill_no = %s AND m.bill_type = %s ORDER BY m.sno", [bill_no, BILL_TYPE],
    )
    extra = GstInvoiceExtra.objects.filter(bill_no=bill_no).first()
    adjustments = []
    for i in range(1, 5):
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
        "bill_no": _clean(h["bill_no"]), "date": h["b_date"].isoformat() if h["b_date"] else "",
        "ca_cr": _clean(h["ca_cr"]) or "CR", "chk_order": _clean(h["chk_ord"]) or "N",
        "party_code": "" if is_cash else _clean(h["p_code"]),
        "party_name": "" if is_cash else _clean(h["cname"]) or "",
        "party_address": "" if is_cash else ", ".join(
            p for p in [_clean(h["cadd1"]), _clean(h["cadd2"])] if p
        ),
        "city": "" if is_cash else _clean(h["cadd3"]) or "",
        "party_state_code": "" if is_cash else _clean(h["gscode"]) or "",
        "party_state_name": "" if is_cash else _clean(h["stname"]) or "",
        "party_pin": "" if is_cash else _clean(h["p_pin"]) or "",
        "party_transport": "" if is_cash else _clean(h["p_transport"]) or "",
        "cash_party_name": _clean(h["c_party"]) if is_cash else "",
        "cash_party_city": _clean(h["c_city"]) if is_cash else "",
        "gst_no": _clean(h["p_gst_no"]) or "", "phone": _clean(h["cphno"]) or "",
        "supply_type": _clean(h["cstat"]) or "W",
        "consignee_name": _clean(h["cname"]) or "", "consignee_address": _clean(h["cadd"]) or "",
        "order_no": _clean(h["ord_no"]) or "", "order_date": h["od_dt"].isoformat() if h["od_dt"] else "",
        "gr_no": _clean(h["gr_no"]) or "", "gr_date": h["gr_dt"].isoformat() if h["gr_dt"] else "",
        "transport": _clean(h["trans"]) or "", "remarks": _clean(h["remk"]) or "",
        "vehicle_no": _clean(h["vehi_no"]) or "",
        "freight": f"{_d(h['fr_amt']):.2f}", "freight_rate": f"{_d(h['fr_rt']):.2f}",
        "freight_gst": f"{_d(h['fr_amt1']):.2f}",
        "freight_ledger_code": extra.freight_ledger_code if extra else "",
        "freight_gst_ledger_code": extra.freight_gst_ledger_code if extra else "",
        "amount": f"{_d(h['amount']):.2f}", "gst_amount": f"{_d(h['gst_amt']):.2f}",
        "net_amount": f"{_d(h['n_amount']):.2f}",
        "adjustments": adjustments,
        "items": [{
            "item_code": _clean(r["i_code"]), "item_name": _clean(r["i_name"]) or "",
            "hsn_code": _clean(r["hs_code"]) or "", "unit": _clean(r["unit"]) or "",
            "order_no": _clean(r["order_no"]) or "", "qty": f"{_d(r['qty']):.3f}",
            "rate": f"{_d(r['rate']):.2f}", "gst_pct": f"{_d(r['gst']):.2f}",
            "amount": f"{_d(r['amount']):.2f}", "active": True, "particular": "",
        } for r in items],
        "date_of_supply": extra.date_of_supply.isoformat() if extra and extra.date_of_supply else "",
        "time_of_supply": extra.time_of_supply if extra else "",
        "place_of_supply": extra.place_of_supply if extra else "",
        "eway_no": extra.eway_no if extra else "",
        "eway_date": extra.eway_date.isoformat() if extra and extra.eway_date else "",
        "reverse_charge": extra.reverse_charge if extra else False,
    }


# --- print -------------------------------------------------------------------------------

def get_share_token(bill_no):
    """Token for a public, no-login link to this invoice's PDF (for sharing e.g.
    over WhatsApp) -- reuses one already issued for this invoice if it's still
    valid, rather than minting (and invalidating) a new one on every share."""
    from .models import GstInvoiceShareLink

    if not get_invoice(bill_no):
        return None
    return GstInvoiceShareLink.get_or_create_for(bill_no).token


def get_bill_no_by_share_token(token):
    """The bill_no a public share link's token points to, or None if the token
    is unknown, expired, or has been revoked."""
    from .models import GstInvoiceShareLink

    link = GstInvoiceShareLink.objects.filter(token=token).first()
    if not link or not link.is_valid():
        return None
    return link.bill_no


def print_data(bill_no):
    """Tax Invoice print view: same get_invoice() data, plus each line split into its
    own CGST+SGST (within state) or IGST (interstate) rate/amount -- identical layout
    to apps.spare_invoice's own print_data(), since both bill types share the exact
    same legacy VFP report (``gpinvex1``, filtered by bill_type)."""
    data = get_invoice(bill_no)
    if not data:
        return None
    interstate = (data["supply_type"] or "W").upper() == "I"
    cgst_total = sgst_total = igst_total = Decimal("0")
    cgst_by_rate, sgst_by_rate, igst_by_rate = {}, {}, {}
    for l in data["items"]:
        l["qty"] = f"{_d(l['qty']):.0f}"  # printed Qty is whole units (matches the legacy Tax Invoice layout)
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


def _delete_legacy(bill_no):
    _exec("DELETE FROM i_master WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE])
    _exec("DELETE FROM bill WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE])
    _reverse_ledger(bill_no)
    GstInvoiceExtra.objects.filter(bill_no=bill_no).delete()


def save_invoice(payload, key=None, username=""):
    _require_writes()
    bill_date = _date(payload.get("date"))
    if not bill_date:
        raise GstInvoiceError("Fix the highlighted fields.", {"date": "Date is required."})
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
    freight_code = (payload.get("freight_ledger_code") or "").strip().upper()
    freight_gst_code = (payload.get("freight_gst_ledger_code") or "").strip().upper()
    if freight and not freight_code:
        raise GstInvoiceError("Fix the highlighted fields.",
                               {"freight_ledger_code": "Freight is non-zero -- enter the ledger code to credit it to."})
    if freight and freight_gst_pct and not freight_gst_code:
        raise GstInvoiceError("Fix the highlighted fields.",
                               {"freight_gst_ledger_code": "Enter the ledger code for GST on freight."})
    accounts = _gst_accounts()
    totals = compute_totals(lines, supply_type, freight, freight_gst_pct, adjustments)

    with transaction.atomic(using="legacy"):
        if key:
            bill_no = key
            if not _rows("SELECT bill_no FROM bill WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE]):
                raise GstInvoiceError("This GST invoice no longer exists.")
            _exec("DELETE FROM i_master WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE])
            _reverse_ledger(bill_no)
            vno = _next_vno(bill_date)
        else:
            bill_no = _allocate_no()
            # Scoped by div too -- bill_no collides with old div='OL' historical
            # rows for this same bill_type (confirmed real data, see
            # spare_invoice.services' own module docstring on this), which are
            # a different division and not a real conflict with the row this
            # save is about to create (always div='SP'). An unscoped check here
            # false-positived on every single Add once the counter reached a
            # number an old OL row already used, blocking new invoices outright.
            if _rows("SELECT bill_no FROM bill WHERE bill_no = %s AND bill_type = %s AND div = %s", [bill_no, BILL_TYPE, DIV]):
                raise GstInvoiceError("This bill no. already exists.")
            vno = _next_vno(bill_date)

        for n, l in enumerate(lines, start=1):
            _exec(
                "INSERT INTO i_master (bill_no, div, date, p_code, sno, i_code, hs_code, unit, amount, "
                "gst, gst_amt, cash, bill_type, cstat, order_no, qty, rate, stts, uname) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [bill_no, DIV, bill_date, party_code, n, l["item_code"], l["hsn_code"], l["unit"],
                 l["amount"], l["gst_pct"], l["gst_amount"], "C" if is_cash else "", BILL_TYPE, supply_type,
                 l["order_no"], l["qty"], l["rate"], "S", username[:10]],
            )

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
        for i in range(1, 5):
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
            "ord_no": (payload.get("order_no") or "").strip(), "od_dt": _date(payload.get("order_date")),
            "gr_no": (payload.get("gr_no") or "").strip(), "gr_dt": _date(payload.get("gr_date")),
            "trans": (payload.get("transport") or "").strip(), "remk": (payload.get("remarks") or "")[:40],
            "vehi_no": (payload.get("vehicle_no") or "").strip(),
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
            _exec(f"UPDATE bill SET {set_clause} WHERE bill_no = %s AND bill_type = %s",
                  values + [bill_no, BILL_TYPE])
        else:
            _exec(
                f"INSERT INTO bill (bill_no, {', '.join(cols)}) VALUES (%s, {placeholders})",
                [bill_no] + values,
            )

        _post_ledger(bill_no, bill_date, vno, is_cash, party_code, cash_party_name, totals, accounts,
                     adjustments, freight_code, freight_gst_code, username)

        GstInvoiceExtra.objects.update_or_create(
            bill_no=bill_no,
            defaults={
                "date_of_supply": _date(payload.get("date_of_supply")),
                "time_of_supply": (payload.get("time_of_supply") or "")[:10],
                "place_of_supply": (payload.get("place_of_supply") or "")[:40],
                "eway_no": (payload.get("eway_no") or "")[:20],
                "eway_date": _date(payload.get("eway_date")),
                "reverse_charge": bool(payload.get("reverse_charge")),
                "freight_ledger_code": freight_code, "freight_gst_ledger_code": freight_gst_code,
            },
        )

    return {"bill_no": bill_no}


def delete_invoice(bill_no):
    _require_writes()
    with transaction.atomic(using="legacy"):
        if not _rows("SELECT bill_no FROM bill WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE]):
            raise GstInvoiceError("This GST invoice no longer exists.")
        _delete_legacy(bill_no)
        row = _rows("SELECT gb_inv_no FROM inv_no")
        if row and str(int(_d(row[0]["gb_inv_no"]))) == str(bill_no):
            _exec("UPDATE inv_no SET gb_inv_no = %s", [int(bill_no) - 1])

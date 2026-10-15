"""
Money Receipt Entry (old VFP form "payrecfrm.scx" / "MONEY RECEIPT ENTRY").

Collection against a customer's outstanding sale invoices (``bill``, any
``bill_type`` -- unlike GST Invoice/Spare Part Invoice, a receipt isn't
scoped to one bill type, it can clear bills from both at once), by CASH,
CHEQUE or RTGS. Mirrors the real VFP ``cmdconfirm.Click``/``deldata`` logic
field-for-field, including its own quirks (see ``_recompute_amount_adjusted``
below) -- this project's convention is to port the legacy behaviour exactly,
not to improve on it.

Tables (all pre-existing, shared with other modules -- see each table's own
column list confirmed directly against the real DB before writing this):
  * ``bill``    -- the same header table GST Invoice/Spare Part Invoice use;
                   a pending bill is any row with ``pmt_rcd = 'N'``, read
                   across every ``bill_type`` and ``div`` for this party, not
                   just one of them.
  * ``col``     -- one row per bill actually adjusted by a receipt (the
                   real VFP "collection against this bill" history row).
  * ``colh``    -- one row per confirmed receipt (slip/voucher header) --
                   the "Money Receipt History" grid on this screen reads
                   this table, scoped to the selected party.
  * ``adv_fil`` -- unadjusted advance held against a party (receipt amount
                   left over after every selected bill is fully covered).
  * ``trans``   -- the shared ledger-posting table every other module here
                   already writes to, same shape.
  * ``vno``     -- per-date voucher-number counters (``cvvno``/``jvvno``),
                   same table/columns apps.gst_invoice/apps.spare_invoice's
                   own ``_next_vno()`` use, just a different column pair.
  * ``inv_no``  -- shared numbering-counters table; ``rcpt_no`` is this
                   screen's own CASH-mode receipt-number counter.

Ledger codes (confirmed against gled_mst, not guessed):
  * CASH_LEDGER_CODE = "C001" (CASH IN HAND) -- VFP global ``pcashcode``.
  * CASH_DISCOUNT_LEDGER_CODE = "D002" (DISCOUNT A/C) -- VFP global
    ``pcdcode``, confirmed with the project owner after gled_mst search.
  * TDS_LEDGER_CODE = "2208" -- the VFP source's own hardcoded literal for
    the T.D.S column. This code does NOT exist in this company's gled_mst
    (confirmed by search); the project owner explicitly asked to keep it
    exactly as the legacy source has it rather than drop the column, so a
    ``trans`` row referencing it will post against a ledger code gled_mst
    doesn't yet have an entry for, until one is added there separately.
  * The party itself is used as its own ledger code for the debtor leg
    (``tcode = party_code``), matching the identical, already-approved
    convention apps.gst_invoice._post_ledger uses for the very same
    "credit the party" leg -- the VFP source's own ``a->code`` reference
    isn't resolvable from the pasted snippets alone, so this project's own
    established local convention is used instead of guessing at a
    different meaning.

Deliberately NOT implemented (flagged, not guessed):
  * Cheque dishonour handling (colh.dishonour/ch_dt/b_charge) -- no
    cheque-dishonour workflow was specified for this screen; those columns
    are left untouched (NULL/blank) on every row this module writes.
  * PRINT (the commented-out ``REPORT FORM prcpt PREVIEW`` in the VFP
    source) -- no printed layout was supplied.
"""
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import connections, transaction

DIV = "SP"
CASH_LEDGER_CODE = "C001"
CASH_DISCOUNT_LEDGER_CODE = "D002"
TDS_LEDGER_CODE = "2208"
MODE_CHOICES = {"CA": "CASH", "CH": "CHEQUE", "RT": "RTGS"}


class MoneyReceiptError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise MoneyReceiptError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


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


def _q2(value):
    return _d(value).quantize(Decimal("0.01"))


def _date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# --- party / bank help (same query shape as apps.gst_invoice.services) -----------------

def search_parties(q):
    q = (q or "").strip().upper()
    if q:
        rows = _rows("SELECT ccode, cname, cadd3 FROM cust_mst WHERE UPPER(cname) LIKE %s ORDER BY cname", [f"%{q}%"])
    else:
        rows = _rows("SELECT ccode, cname, cadd3 FROM cust_mst ORDER BY cname")
    return [{"code": _clean(r["ccode"]), "name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or ""}
            for r in rows[:20]]


def party_detail(code):
    rows = _rows("SELECT ccode, cname, cadd3 FROM cust_mst WHERE ccode = %s", [(code or "").strip().upper()])
    if not rows:
        return None
    r = rows[0]
    return {"code": _clean(r["ccode"]), "name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or ""}


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


# --- party summary figures (VFP's PARTYHELP onSelect block) -----------------------------

def previous_advance(party_code):
    rows = _rows("SELECT amount FROM adv_fil WHERE p_code = %s", [party_code])
    return _d(rows[0]["amount"]) if rows else Decimal("0")


def ledger_balance(party_code):
    """VFP: mopbal = a->cyob + sum(D trans) - sum(C trans) for this party's own code."""
    cust = _rows("SELECT cyob FROM cust_mst WHERE ccode = %s", [party_code])
    opening = _d(cust[0]["cyob"]) if cust else Decimal("0")
    dc = _rows(
        "SELECT tdbcr, SUM(tamt) AS total FROM trans WHERE tccode = %s GROUP BY tdbcr", [party_code],
    )
    debit = credit = Decimal("0")
    for r in dc:
        if _clean(r["tdbcr"]) == "D":
            debit = _d(r["total"])
        elif _clean(r["tdbcr"]) == "C":
            credit = _d(r["total"])
    return opening + debit - credit


def next_cash_receipt_no():
    rows = _rows("SELECT rcpt_no FROM inv_no")
    return int(_d(rows[0]["rcpt_no"])) + 1 if rows else 1


def party_outstanding_report(run_date, party_code=None):
    """Party Wise Outstanding -- direct port of the VFP report "posparty"
    (and its Excel-export twin), for the standalone Party Outstanding screen
    (Money Receipts > Party Outstanding). party_code=None means every party
    (VFP: thisform.tsa.value='A'), matching ALL/SINGLE scope.

    NOTE on the balance formula: this report's own source computes
    ``n_amount - amt_rcd - c_note1 + d_note1 + int_amt - c_dis`` (int_amt
    ADDED) -- the opposite sign from this app's own Money Receipt Entry
    screen (pending_bills() below: ``... - int_amt - c_dis``), which came
    from a different, earlier-supplied VFP source for that screen's own
    bill-allocation grid. Both are real, directly-pasted legacy sources that
    disagree on this one sign; rather than silently picking one to reconcile
    them, this function follows the posparty report's own formula exactly
    (since that's what it's reproducing), while pending_bills() is left as
    the Money Receipt Entry screen's own formula. Flagged for the project
    owner to resolve which is actually correct, not guessed here.
    """
    party_rows = _rows(
        "SELECT ccode, cname, cadd3, cphno FROM cust_mst" + (" WHERE ccode = %s" if party_code else ""),
        [party_code] if party_code else [],
    )
    groups = []
    g_totals = {"below_30": Decimal("0"), "between_31_60": Decimal("0"),
                "between_61_90": Decimal("0"), "above_90": Decimal("0")}
    g_balance = Decimal("0")
    g_advance = Decimal("0")

    for p in party_rows:
        ccode = _clean(p["ccode"])
        advance = previous_advance(ccode)
        bills = _rows(
            "SELECT bill_no, b_date, n_amount, amt_rcd, c_note1, d_note1, int_amt, c_dis "
            "FROM bill WHERE p_code = %s AND pmt_rcd <> 'Y' AND b_date <= %s ORDER BY b_date",
            [ccode, run_date],
        )
        if advance == 0 and not bills:
            continue  # posparty: a party contributes nothing to list without either

        rows_out = []
        totals = {"below_30": Decimal("0"), "between_31_60": Decimal("0"),
                  "between_61_90": Decimal("0"), "above_90": Decimal("0")}
        tbalamt = -advance
        for b in bills:
            mbalance = (
                _d(b["n_amount"]) - _d(b["amt_rcd"]) - _d(b["c_note1"]) + _d(b["d_note1"])
                + _d(b["int_amt"]) - _d(b["c_dis"])
            )
            tbalamt += mbalance
            b_date = b["b_date"]
            day_diff = (run_date - b_date).days if b_date else 0
            bucket = ("below_30" if day_diff <= 30 else "between_31_60" if day_diff <= 60
                      else "between_61_90" if day_diff <= 90 else "above_90")
            totals[bucket] += mbalance
            rows_out.append({
                "bill_no": _clean(b["bill_no"]), "bill_date": b_date.isoformat() if b_date else "",
                "bill_amount": f"{_d(b['n_amount']):.2f}", "amount_received": f"{_d(b['amt_rcd']):.2f}",
                "dr_note": f"{_d(b['d_note1']):.2f}", "cr_note": f"{_d(b['c_note1']):.2f}",
                "balance": f"{mbalance:.2f}", "bucket": bucket,
            })

        ledger_bal = ledger_balance(ccode)
        groups.append({
            "party_code": ccode, "party_name": _clean(p["cname"]) or "",
            "city": _clean(p["cadd3"]) or "", "phone": _clean(p["cphno"]) or "",
            "advance": f"{advance:.2f}", "rows": rows_out,
            "below_30": f"{totals['below_30']:.2f}", "between_31_60": f"{totals['between_31_60']:.2f}",
            "between_61_90": f"{totals['between_61_90']:.2f}", "above_90": f"{totals['above_90']:.2f}",
            "total_balance": f"{tbalamt:.2f}", "ledger_balance": f"{ledger_bal:.2f}",
            "ledger_mismatch": abs(tbalamt - abs(ledger_bal)) > Decimal("0.01"),
        })
        for k in g_totals:
            g_totals[k] += totals[k]
        g_balance += tbalamt
        g_advance += advance

    return {
        "groups": groups,
        "below_30": f"{g_totals['below_30']:.2f}", "between_31_60": f"{g_totals['between_31_60']:.2f}",
        "between_61_90": f"{g_totals['between_61_90']:.2f}", "above_90": f"{g_totals['above_90']:.2f}",
        "total_balance": f"{g_balance:.2f}", "advance": f"{g_advance:.2f}",
        "net_outstanding": f"{(g_balance - g_advance):.2f}",
    }


# --- pending bills (VFP: sele 5, set filt to p_code=... and pmt_rcd='N') ----------------

def pending_bills(party_code):
    rows = _rows(
        "SELECT bill_type, div, bill_no, b_date, n_amount, amt_rcd, c_note1, d_note1, int_amt, c_dis "
        "FROM bill WHERE p_code = %s AND pmt_rcd = 'N' ORDER BY b_date, bill_no",
        [party_code],
    )
    out = []
    for r in rows:
        n_amount, d_note1 = _d(r["n_amount"]), _d(r["d_note1"])
        balance = n_amount - _d(r["amt_rcd"]) - _d(r["c_note1"]) + d_note1 - _d(r["int_amt"]) - _d(r["c_dis"])
        out.append({
            "bill_type": _clean(r["bill_type"]), "div": _clean(r["div"]) or "",
            "bill_no": _clean(r["bill_no"]), "bill_date": r["b_date"].isoformat() if r["b_date"] else "",
            "inv_amount": f"{(n_amount + d_note1):.2f}", "balance_amt": f"{balance:.2f}",
        })
    return out


# --- history grid (colh, scoped to this party) ------------------------------------------

def history_rows(party_code, exclude=None):
    """Past Money Receipts for this party -- excludes the receipt currently
    being viewed, if any (identified by (p_code, chq_no, slip_dt) -- see
    list_receipts' docstring note on why (div, vou_no) isn't a safe key)."""
    rows = _rows(
        "SELECT div, vou_no, slip_dt, chq_no, chq_dt, bank_code, amount, total_amt FROM colh "
        "WHERE p_code = %s ORDER BY slip_dt DESC, vou_no DESC",
        [party_code],
    )
    out = []
    for r in rows:
        slip_dt_iso = r["slip_dt"].isoformat() if r["slip_dt"] else ""
        chq_no = _clean(r["chq_no"]) or ""
        if exclude and (party_code, chq_no, slip_dt_iso) == exclude:
            continue
        out.append({
            "div": _clean(r["div"]), "vou_no": _clean(r["vou_no"]), "slip_dt": slip_dt_iso,
            "chq_no": chq_no, "chq_dt": r["chq_dt"].isoformat() if r["chq_dt"] else "",
            "bank_code": _clean(r["bank_code"]) or "",
            "amount": f"{_d(r['amount']):.2f}", "total_amount": f"{_d(r['total_amt']):.2f}",
        })
    return out


# --- master list -------------------------------------------------------------------------

def list_receipts(start, end, search=""):
    # Identified by (p_code, chq_no, slip_dt) -- confirmed unique across every
    # existing colh row, unlike (div, vou_no): real historical rows all have
    # div='' and mostly vou_no='1' (vou_no was evidently never reliably
    # populated in production), so that pair collides on 15 of 18 real rows.
    search = (search or "").strip().upper()
    rows = _rows(
        "SELECT h.div, h.vou_no, h.slip_dt, h.p_code, h.chq_no, h.total_amt, c.cname, c.cadd3 "
        "FROM colh h LEFT JOIN cust_mst c ON c.ccode = h.p_code "
        "WHERE h.slip_dt >= %s AND h.slip_dt <= %s ORDER BY h.slip_dt, h.vou_no",
        [start, end],
    )
    out = []
    for r in rows:
        name = _clean(r["cname"]) or ""
        if search and not name.upper().startswith(search):
            continue
        p_code, chq_no = _clean(r["p_code"]), _clean(r["chq_no"]) or ""
        slip_dt = r["slip_dt"].isoformat() if r["slip_dt"] else ""
        out.append({
            "key": f"{p_code}|{chq_no}|{slip_dt}", "p_code": p_code, "chq_no": chq_no, "slip_dt": slip_dt,
            "date": slip_dt, "party": name, "city": _clean(r["cadd3"]) or "",
            "total_amount": f"{_d(r['total_amt']):.2f}",
        })
    return out


def get_receipt(p_code, chq_no, slip_dt):
    rows = _rows(
        "SELECT h.*, c.cname, c.cadd3 FROM colh h LEFT JOIN cust_mst c ON c.ccode = h.p_code "
        "WHERE h.p_code = %s AND h.chq_no = %s AND h.slip_dt = %s", [p_code, chq_no, _date(slip_dt)],
    )
    if not rows:
        return None
    h = rows[0]
    # colh has no mode/type column of its own -- CASH is reliably identifiable
    # (blank bank_code, see save_receipt), but CHEQUE vs RTGS can't be told
    # apart after the fact from this table alone, so VIEW just shows CHEQUE's
    # labels for either; it's cosmetic only (doesn't affect delete/reversal).
    mode = "CA" if not _clean(h["bank_code"]) else "CH"
    lines = _rows(
        "SELECT div, bill_no, b_date, b_amt, c_dis, int_amt, amount, bill_type FROM col "
        "WHERE nar = %s AND p_code = %s", [_clean(h["chq_no"]), _clean(h["p_code"])],
    )
    return {
        "div": _clean(h["div"]), "vou_no": _clean(h["vou_no"]),
        "party_code": _clean(h["p_code"]), "party_name": _clean(h["cname"]) or "",
        "party_city": _clean(h["cadd3"]) or "",
        "mode": mode, "bank_code": _clean(h["bank_code"]) or "",
        "slip_dt": h["slip_dt"].isoformat() if h["slip_dt"] else "",
        "chq_no": _clean(h["chq_no"]) or "", "chq_dt": h["chq_dt"].isoformat() if h["chq_dt"] else "",
        "amount": f"{_d(h['amount']):.2f}", "prev_adv": f"{_d(h['prev_adv']):.2f}",
        "total_amt": f"{_d(h['total_amt']):.2f}", "pend_adv": f"{_d(h['pend_adv']):.2f}",
        "lines": [
            {"div": _clean(l["div"]) or "", "bill_no": _clean(l["bill_no"]),
             "bill_date": l["b_date"].isoformat() if l["b_date"] else "",
             "inv_amount": f"{_d(l['b_amt']):.2f}", "cash_discount": f"{_d(l['c_dis']):.2f}",
             "tds_amt": f"{_d(l['int_amt']):.2f}", "amount_adjusted": f"{_d(l['amount']):.2f}",
             "bill_type": _clean(l["bill_type"]) or ""}
            for l in lines
        ],
    }


# --- save / delete (VFP cmdconfirm.Click / deldata) ---------------------------------------

def _next_vno(mode, slip_date):
    """VFP: mm = mtype+'vno'; repl &mm with &mm+1 -- CV (cash/no distinct journal)
    for CASH, JV for CHEQUE/RTGS, against the vno table's per-date counter row.
    WITH (UPDLOCK, HOLDLOCK) matches every other numbering counter in this
    codebase (e.g. apps.spare_invoice._allocate_no()) -- without it, two
    concurrent saves on the same date can both read the same current value
    and allocate the identical voucher number."""
    field = "jvvno" if mode in ("CH", "RT") else "cvvno"
    with connections["legacy"].cursor() as cur:
        cur.execute(f"SELECT {field} FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [slip_date])
        row = cur.fetchone()
        if row:
            new_no = int(_d(row[0])) + 1
            cur.execute(f"UPDATE vno SET {field} = %s WHERE date = %s", [new_no, slip_date])
        else:
            new_no = 1
            cur.execute(f"INSERT INTO vno (date, {field}) VALUES (%s, %s)", [slip_date, new_no])
    return new_no


def save_receipt(payload, username=""):
    """payload: mode ('CA'/'CH'/'RT'), slip_date, amount_received, party_code,
    bank_code (blank for CASH), chq_no, chq_dt, lines: [{bill_type, div,
    bill_no, bill_date, inv_amount, balance_amt, cash_discount, tds_amt,
    amount_adjusted}, ...] -- only lines with amount_adjusted > 0 are posted,
    matching the VFP loop's own ``val(.dkgrid.textmatrix(i,8))>0`` guard."""
    _require_writes()
    mode = (payload.get("mode") or "CA").upper()
    slip_date = _date(payload.get("slip_date"))
    if not slip_date:
        raise MoneyReceiptError("Fix the highlighted fields.", {"slip_date": "Date is required."})
    party_code = (payload.get("party_code") or "").strip().upper()
    if not party_code:
        raise MoneyReceiptError("Fix the highlighted fields.", {"party_code": "Select a party."})
    amount_received = _d(payload.get("amount_received"))
    if amount_received <= 0:
        raise MoneyReceiptError("Fix the highlighted fields.", {"amount_received": "Invalid Amount."})
    lines = [l for l in (payload.get("lines") or []) if _d(l.get("amount_adjusted")) != 0]

    total_outstanding = sum((_d(l["balance_amt"]) for l in payload.get("lines") or []), Decimal("0"))
    mbalance = amount_received
    totcd = totint = Decimal("0")
    touched = False
    for l in lines:
        adj = _d(l["amount_adjusted"])
        cash_dis = _d(l.get("cash_discount"))
        tds = _d(l.get("tds_amt"))
        mamt = adj if cash_dis > 0 else adj + tds
        if mamt > 0:
            touched = True
            mbalance -= mamt
            totcd += cash_dis
            totint += tds

    # VFP: if .tos.value-.tamount.value>0 and mbalance>0 -> "ADJUST COMPLETE CHEQUE AMOUNT"
    if total_outstanding - amount_received > 0 and mbalance > 0:
        raise MoneyReceiptError(
            "ADJUST COMPLETE CHEQUE AMOUNT", {"amount_received": "Allocate the full amount received."},
        )

    with transaction.atomic(using="legacy"):
        vou_no = str(_next_vno(mode, slip_date))
        if mode == "CA":
            # Row-locked for the same reason as _next_vno above -- this is
            # the counter mr_next_cash_no()/the Add-mode screen's own preview
            # reads too, so a stale read here would hand out a receipt number
            # two concurrent CASH saves could both grab.
            with connections["legacy"].cursor() as cur:
                cur.execute("SELECT rcpt_no FROM inv_no WITH (UPDLOCK, HOLDLOCK)")
                row = cur.fetchone()
                current = int(_d(row[0])) if row else 0
                typed = int(_d(payload.get("chq_no")) or 0)
                new_rcpt_no = typed if typed > current else current + 1
                cur.execute("UPDATE inv_no SET rcpt_no = %s", [new_rcpt_no])

        mtcode = (payload.get("bank_code") or "").strip().upper() if mode != "CA" else CASH_LEDGER_CODE
        mtnar = {"RT": "RTGS No.", "CH": "Chq.No.", "CA": "Rcpt.No."}[mode] + (payload.get("chq_no") or "")
        username = (username or "")[:10]

        def post_trans(tdbcr, tcode, amount, tccode="", narration_prefix=""):
            if amount == 0:
                return
            # nar carries the chq_no -- same field delete_receipt() filters
            # trans on (together with tdate+tdoc) to find exactly this
            # receipt's own rows, since (div, vou_no) alone isn't reliably
            # unique in this table's real historical data.
            _exec(
                "INSERT INTO trans (ttype, tdoc, tdate, tcode, tccode, tdbcr, tnar1, nar, tamt, div, uname, bill_type) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                ["JV" if mode in ("CH", "RT") else "CV", vou_no, slip_date, tcode, tccode, tdbcr,
                 (narration_prefix + mtnar)[:60], payload.get("chq_no") or "", amount, DIV, username, ""],
            )

        post_trans("D", mtcode, amount_received, narration_prefix="Paym. Recd. " if touched else "Adv. Recd. ")

        for l in lines:
            adj = _d(l["amount_adjusted"])
            if adj <= 0:
                continue
            bill_type, div, bill_no = l["bill_type"], l.get("div") or "", l["bill_no"]
            cash_dis, tds = _d(l.get("cash_discount")), _d(l.get("tds_amt"))
            with connections["legacy"].cursor() as cur:
                # c_dis/int_amt accumulate across multiple partial payments
                # against the same bill (matching delete_receipt's own reversal,
                # which already does c_dis = c_dis - %s) -- a plain c_dis = %s
                # here would silently erase an earlier payment's discount/TDS
                # the moment a second partial payment was saved against the
                # same bill, corrupting pending_bills()'s balance formula.
                cur.execute(
                    "UPDATE bill SET amt_rcd = amt_rcd + %s, c_dis = c_dis + %s, int_amt = int_amt + %s, "
                    "pmt_rcd = CASE WHEN n_amount - (amt_rcd + %s) - c_note1 + d_note1 - (int_amt + %s) - (c_dis + %s) = 0 "
                    "THEN 'Y' ELSE pmt_rcd END "
                    "WHERE bill_no = %s AND bill_type = %s AND div = %s",
                    [adj, cash_dis, tds, adj, tds, cash_dis, bill_no, bill_type, div],
                )
            _exec(
                "INSERT INTO col (slip_dt, nar, p_code, div, bill_no, b_date, b_amt, c_dis, int_amt, amount, "
                "bill_type, uname) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [slip_date, payload.get("chq_no") or "", party_code, div, bill_no, _date(l.get("bill_date")),
                 _d(l["inv_amount"]), cash_dis, tds, adj, bill_type, username],
            )
            if cash_dis > 0:
                post_trans("D", CASH_DISCOUNT_LEDGER_CODE, cash_dis, tccode=party_code,
                           narration_prefix=f"Dis. Allowed on Inv. No.{bill_no}")
            if tds > 0:
                post_trans("D", TDS_LEDGER_CODE, tds, tccode=party_code, narration_prefix=f"T.D.S {bill_no}")

        if amount_received - mbalance > 0:
            post_trans("C", party_code, amount_received - mbalance, tccode=party_code, narration_prefix="")

        if mbalance == amount_received:
            _exec(
                "INSERT INTO col (slip_dt, nar, p_code, div, bill_no, b_date, amount, uname) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                [slip_date, payload.get("chq_no") or "", party_code, DIV, "ADV.", slip_date, amount_received, username],
            )

        if mbalance > 0:
            existing = _rows("SELECT amount FROM adv_fil WHERE p_code = %s", [party_code])
            if existing:
                _exec("UPDATE adv_fil SET amount = amount + %s WHERE p_code = %s", [mbalance, party_code])
            else:
                _exec("INSERT INTO adv_fil (p_code, amount) VALUES (%s, %s)", [party_code, mbalance])
            post_trans("C", party_code, mbalance, tccode=party_code, narration_prefix="Adv. Recd. ")
        elif mbalance < 0:
            existing = _rows("SELECT amount FROM adv_fil WHERE p_code = %s", [party_code])
            if existing:
                new_amt = _d(existing[0]["amount"]) - abs(mbalance)
                if new_amt <= 0:
                    _exec("DELETE FROM adv_fil WHERE p_code = %s", [party_code])
                else:
                    _exec("UPDATE adv_fil SET amount = %s WHERE p_code = %s", [new_amt, party_code])
            else:
                _exec("INSERT INTO adv_fil (p_code, amount) VALUES (%s, %s)", [party_code, abs(mbalance)])

        if totcd > 0:
            post_trans("C", party_code, totcd, tccode=party_code, narration_prefix="Discount Recd. ")
        if totint > 0:
            post_trans("C", party_code, totint, tccode=party_code, narration_prefix="T.D.S ")

        _exec(
            "INSERT INTO colh (bank_code, slip_no, slip_dt, p_code, amount, prev_adv, total_amt, pend_adv, "
            "chq_no, chq_dt, vou_no, div, uname) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [mtcode if mode != "CA" else "", mode, slip_date, party_code, amount_received,
             _d(payload.get("prev_adv")), amount_received, mbalance, payload.get("chq_no") or "",
             _date(payload.get("chq_dt")), vou_no, DIV, username],
        )

    return {"div": DIV, "vou_no": vou_no}


def delete_receipt(p_code, chq_no, slip_dt):
    """VFP deldata/mflag=3 case: reverses adv_fil, every bill this receipt
    touched (via col), every trans row this receipt posted, then the colh
    row itself. Identified by (p_code, chq_no, slip_dt) -- see list_receipts'
    docstring note on why (div, vou_no) isn't a safe key for this table."""
    _require_writes()
    with transaction.atomic(using="legacy"):
        header = _rows(
            "SELECT * FROM colh WHERE p_code = %s AND chq_no = %s AND slip_dt = %s",
            [p_code, chq_no, _date(slip_dt)],
        )
        if not header:
            raise MoneyReceiptError("This Money Receipt no longer exists.")
        h = header[0]
        party_code, pend_adv, chq_no, div, vou_no = (
            _clean(h["p_code"]), _d(h["pend_adv"]), _clean(h["chq_no"]), _clean(h["div"]), _clean(h["vou_no"]),
        )

        existing = _rows("SELECT amount FROM adv_fil WHERE p_code = %s", [party_code])
        if existing:
            new_amt = _d(existing[0]["amount"]) - pend_adv
            if new_amt <= 0:
                _exec("DELETE FROM adv_fil WHERE p_code = %s", [party_code])
            else:
                _exec("UPDATE adv_fil SET amount = %s WHERE p_code = %s", [new_amt, party_code])
        elif pend_adv < 0:
            _exec("INSERT INTO adv_fil (p_code, amount) VALUES (%s, %s)", [party_code, -pend_adv])

        lines = _rows(
            "SELECT div, bill_no, bill_type, c_dis, int_amt, amount FROM col WHERE nar = %s AND p_code = %s",
            [chq_no, party_code],
        )
        for l in lines:
            _exec(
                "UPDATE bill SET amt_rcd = amt_rcd - %s, c_dis = c_dis - %s, int_amt = int_amt - %s, pmt_rcd = 'N' "
                "WHERE bill_no = %s AND bill_type = %s AND div = %s",
                [_d(l["amount"]), _d(l["c_dis"]), _d(l["int_amt"]), l["bill_no"], l["bill_type"], l["div"]],
            )
        _exec("DELETE FROM col WHERE nar = %s AND p_code = %s", [chq_no, party_code])
        # (div, vou_no) alone can match other, unrelated historical receipts
        # (confirmed real collisions -- see module docstring), so trans rows
        # are scoped by date+nar+tdoc together, matching the real VFP delete
        # routine's own filter, not just tdoc+div.
        _exec(
            "DELETE FROM trans WHERE tdate = %s AND nar = %s AND tdoc = %s AND div = %s",
            [h["slip_dt"], chq_no, vou_no, div],
        )
        _exec(
            "DELETE FROM colh WHERE p_code = %s AND chq_no = %s AND slip_dt = %s",
            [party_code, chq_no, h["slip_dt"]],
        )

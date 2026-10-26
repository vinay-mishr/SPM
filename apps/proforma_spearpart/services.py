"""
Performa Invoice (Spearpart) (old VFP form "gPER4" / list "PERFORMA INVOICE
(Spearpart)").

Header lives in ``g_per`` (``bill_type = 'P'``), lines in ``p_mst`` -- separate
tables/columns from apps.proforma_invoice's own 'G' type (which uses ``p_master``,
note no underscore-free "_mst" there) and from apps.spare_invoice's 'P' type
(which lives on ``bill``/``imaster`` entirely). Confirmed real data: 2 real 'P'
rows on g_per, 8 real rows on p_mst for them. Numbered from its OWN counter,
``inv_no.gp_no`` -- not ``gp_inv_no``, which apps.proforma_invoice already owns.

Items come from ``part-mst`` (apps.parts.models.Part's table), not the ``item``
table apps.proforma_invoice's 'G' type uses -- confirmed by the real VFP source's
``use part-mst in 0 ... alia partmst`` and the real p_mst rows' ``unit`` values
("SET") matching part-mst data.

Same as apps.proforma_invoice: per explicit requirement this is a quotation, not
a finalized sale -- no row is ever written to ``trans`` (confirmed the real
``rpldata`` routine's entire ledger section is commented out, same as the 'G'
type), and no stock/order table is touched.

Adds four charge fields over the 'G' type (Packing/Commissioning/Freight/
Insurance -- ``pack_ch``/``commi``/``freight``/``insur`` on ``g_per``), which the
real ``caltotal`` folds into the net amount AFTER GST (GST is computed on item
amount only, matching the real formula:
``gross = gst_total + (item_amount + pack_ch + commi + freight + insur)``).
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import connections, transaction

from .models import ProformaSpearpartExtra

DIV = "SP"
BILL_TYPE = "P"
GST_RATES = (0, 5, 12, 18, 28)
Q2 = Decimal("0.01")


class ProformaSpearpartError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise ProformaSpearpartError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


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


# --- numbering ---------------------------------------------------------------------
#
# Same NULL-counter hazard apps.proforma_invoice._highest_no() already guards
# against: falls back to the real highest existing bill_no (within bill_type='P')
# so a stale/absent ``inv_no.gp_no`` can never collide with real data.

def _highest_no():
    bill_nos = [r["bill_no"] for r in _rows("SELECT bill_no FROM g_per WHERE bill_type = %s", [BILL_TYPE])]
    nums = [int(n) for n in bill_nos if str(n).strip().isdigit()]
    return max(nums) if nums else 0


def next_no():
    rows = _rows("SELECT gp_no FROM inv_no")
    counter = int(_d(rows[0]["gp_no"])) if rows and rows[0]["gp_no"] is not None else 0
    return max(counter, _highest_no()) + 1


def _allocate_no():
    with connections["legacy"].cursor() as cur:
        cur.execute("SELECT gp_no FROM inv_no WITH (UPDLOCK, HOLDLOCK)")
        row = cur.fetchone()
        counter = int(_d(row[0])) if row and row[0] is not None else 0
        new_no = max(counter, _highest_no()) + 1
        cur.execute("UPDATE inv_no SET gp_no = %s", [new_no])
    return str(new_no)


# --- listing ---------------------------------------------------------------------------

def list_invoices(start, end, search=""):
    search = (search or "").strip().upper()
    rows = _rows(
        "SELECT g.bill_no, g.b_date, g.p_code, g.n_amount, c.cname, c.cadd3 "
        "FROM g_per g LEFT JOIN cust_mst c ON c.ccode = g.p_code "
        "WHERE g.bill_type = %s AND g.b_date >= %s AND g.b_date <= %s "
        "ORDER BY g.b_date, g.bill_no",
        [BILL_TYPE, start, end],
    )
    out = []
    for r in rows:
        name = _clean(r["cname"]) or "ACCOUNT NOT FOUND"
        city = _clean(r["cadd3"]) or ""
        bill_no = _clean(r["bill_no"])
        if search and not (
            name.upper().startswith(search) or bill_no.upper().startswith(search) or city.upper().startswith(search)
        ):
            continue
        out.append({
            "key": bill_no, "bill_no": bill_no,
            "date": r["b_date"].isoformat() if r["b_date"] else "",
            "party": name, "city": city,
            "net_amount": f"{_d(r['n_amount']):.2f}",
        })
    return out


# --- item / party lookups for the Add form ----------------------------------------------

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
        'SELECT icod, ides, uom, hs_code, gs_rt, srate FROM [part-mst] WHERE icod = %s',
        [(code or "").strip().upper()],
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "code": _clean(r["icod"]), "name": _clean(r["ides"]) or "", "unit": _clean(r["uom"]) or "",
        "hsn": _clean(r["hs_code"]) or "", "gst_pct": f"{_d(r['gs_rt']):.2f}", "rate": f"{_d(r['srate']):.2f}",
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
        "SELECT ccode, cname, cadd3, gst_no, cstat FROM cust_mst WHERE ccode = %s",
        [(code or "").strip().upper()],
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "code": _clean(r["ccode"]), "name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or "",
        "gst_no": _clean(r["gst_no"]) or "", "supply_type": _clean(r["cstat"]) or "W",
    }


# --- validation --------------------------------------------------------------------------

def _validate(payload):
    errors = {}
    party_code = (payload.get("party_code") or "").strip().upper()
    if not party_code:
        errors["party_code"] = "Select the party."
    elif not _rows("SELECT ccode FROM cust_mst WHERE ccode = %s", [party_code]):
        errors["party_code"] = "Party not found."

    gst_enabled = (payload.get("gst_enabled") or "Y").upper() != "N"
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
        gst_pct = int(_d(part[0]["gs_rt"])) if gst_enabled else 0
        if gst_pct not in GST_RATES:
            errors.setdefault("items", f"Row {n}: GST rate {gst_pct}% isn't 0/5/12/18/28.")
            continue
        amount = _q2(qty * rate)
        lines.append({
            "item_code": code, "hsn_code": (row.get("hsn_code") or "").strip() or _clean(part[0]["hs_code"]) or "",
            "unit": (row.get("unit") or "").strip() or _clean(part[0]["uom"]) or "",
            "qty": qty, "rate": rate, "amount": amount, "gst_pct": gst_pct,
            "gst_amount": _q2(amount * gst_pct / 100),
            "particular": (row.get("particular") or "").strip()[:100],
        })
    if not lines and "items" not in errors:
        errors["items"] = "Add at least one item."
    if errors:
        raise ProformaSpearpartError("Fix the highlighted fields.", errors)
    return party_code, gst_enabled, lines


# --- totals ----------------------------------------------------------------------------

def compute_totals(lines, supply_type, charges, adjustments):
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

    charges_total = charges["pack_ch"] + charges["commi"] + charges["freight"] + charges["insur"]
    assessable = amount + charges_total
    gross = gst_total + assessable

    net = gross
    for adj in adjustments:
        net += adj["amount"] if adj["sign"] == "A" else -adj["amount"]
    net_rounded = net.to_integral_value(rounding=ROUND_HALF_UP)
    diff = net - net_rounded

    return {
        "taxable_by_rate": {r: buckets[r]["taxable"] for r in GST_RATES},
        "gst_detail": gst_detail, "amount": amount, "gst_total": gst_total,
        "charges_total": charges_total, "assessable": assessable, "gross": gross,
        "net": net, "net_rounded": net_rounded, "diff": diff, "interstate": interstate,
    }


# --- save / delete -----------------------------------------------------------------------

def get_invoice(bill_no):
    rows = _rows(
        "SELECT g.*, c.cname, c.cadd3, c.gst_no AS p_gst_no "
        "FROM g_per g LEFT JOIN cust_mst c ON c.ccode = g.p_code "
        "WHERE g.bill_no = %s AND g.bill_type = %s", [bill_no, BILL_TYPE],
    )
    if not rows:
        return None
    h = rows[0]
    items = _rows(
        "SELECT m.i_code, m.unit, m.qty, m.rate, m.amount, m.gst, m.gst_amt, m.hs_code, m.particular, "
        "p.ides AS i_name FROM p_mst m LEFT JOIN [part-mst] p ON p.icod = m.i_code "
        "WHERE m.bill_no = %s AND m.bill_type = %s ORDER BY m.sno", [bill_no, BILL_TYPE],
    )
    extra = ProformaSpearpartExtra.objects.filter(bill_no=bill_no).first()
    return {
        "bill_no": _clean(h["bill_no"]), "date": h["b_date"].isoformat() if h["b_date"] else "",
        "gst_enabled": _clean(h["yn"]) or "Y",
        "party_code": _clean(h["p_code"]), "party_name": _clean(h["cname"]) or "",
        "city": _clean(h["cadd3"]) or "",
        "gst_no": _clean(h["gst_no"]) or (_clean(h["p_gst_no"]) or ""),
        "supply_type": _clean(h["cstat"]) or "W",
        "order_no": _clean(h["ord_no"]) or "", "order_date": h["ord_dt"].isoformat() if h["ord_dt"] else "",
        "pl_no": extra.pl_no if extra else "", "pl_date": extra.pl_date.isoformat() if extra and extra.pl_date else "",
        "others": extra.others if extra else "",
        "remarks": _clean(h["remk"]) or "",
        "pack_ch": f"{_d(h['pack_ch']):.2f}", "commi": f"{_d(h['commi']):.2f}",
        "freight": f"{_d(h['freight']):.2f}", "insur": f"{_d(h['insur']):.2f}",
        "net_amount": f"{_d(h['n_amount']):.2f}",
        # (sign, code) blank together means "no adjustment in this slot" -- a blank
        # SIGN with a real code/amount (seen in real data) means LESS, matching the
        # real VFP caltotal's `iif(.tadj1.value='A', +, -)` (anything not 'A' subtracts).
        "adjustments": [
            {"sign": "A" if (_clean(h.get(f"adj{i}")) or "").upper() == "A" else "S",
             "code": _clean(h.get(f"adj_code{i}")) or "", "amount": f"{_d(h.get(f'adj_amt{i}')):.2f}"}
            for i in (1, 2) if _clean(h.get(f"adj_code{i}")) or _d(h.get(f"adj_amt{i}"))
        ],
        "items": [{
            "item_code": _clean(r["i_code"]), "item_name": _clean(r["i_name"]) or "",
            "hsn_code": _clean(r["hs_code"]) or "", "unit": _clean(r["unit"]) or "",
            "qty": f"{_d(r['qty']):.3f}", "rate": f"{_d(r['rate']):.2f}", "gst_pct": f"{_d(r['gst']):.2f}",
            "amount": f"{_d(r['amount']):.2f}", "particular": _clean(r["particular"]) or "",
        } for r in items],
    }


def _delete_legacy(bill_no):
    _exec("DELETE FROM p_mst WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE])
    _exec("DELETE FROM g_per WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE])
    ProformaSpearpartExtra.objects.filter(bill_no=bill_no).delete()


def save_invoice(payload, key=None, username=""):
    _require_writes()
    bill_date = _date(payload.get("date"))
    if not bill_date:
        raise ProformaSpearpartError("Fix the highlighted fields.", {"date": "Date is required."})
    party_code, gst_enabled, lines = _validate(payload)
    supply_type = (payload.get("supply_type") or "W").upper()
    charges = {
        "pack_ch": _q2(payload.get("pack_ch")), "commi": _q2(payload.get("commi")),
        "freight": _q2(payload.get("freight")), "insur": _q2(payload.get("insur")),
    }
    adjustments = []
    for a in payload.get("adjustments") or []:
        code = (a.get("code") or "").strip().upper()
        amt = _q2(a.get("amount"))
        sign = (a.get("sign") or "A").upper()
        if code and amt:
            adjustments.append({"code": code, "amount": amt, "sign": sign})
    totals = compute_totals(lines, supply_type, charges, adjustments)

    with transaction.atomic(using="legacy"):
        if key:
            bill_no = key
            if not _rows("SELECT bill_no FROM g_per WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE]):
                raise ProformaSpearpartError("This Performa Invoice Sparepart no longer exists.")
            _exec("DELETE FROM p_mst WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE])
        else:
            bill_no = _allocate_no()
            if _rows("SELECT bill_no FROM g_per WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE]):
                raise ProformaSpearpartError("PROFORMA NO. Already Exist")

        for n, l in enumerate(lines, start=1):
            detail = totals["gst_detail"].get(l["gst_pct"], {})
            _exec(
                "INSERT INTO p_mst (bill_no, div, date, p_code, yn, sno, i_code, hs_code, unit, qty, rate, "
                "amount, gst, gst_amt, cgst_rt, cgst_amt, sgst_rt, sgst_amt, igst_rt, igst_amt, stts, cash, "
                "bill_type, cstat, uname, particular) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [bill_no, DIV, bill_date, party_code, "Y" if gst_enabled else "N", n, l["item_code"],
                 l["hsn_code"], l["unit"], l["qty"], l["rate"], l["amount"], l["gst_pct"], l["gst_amount"],
                 detail.get("cgst_rt", Decimal("0")), detail.get("cgst_amt", Decimal("0")),
                 detail.get("sgst_rt", Decimal("0")), detail.get("sgst_amt", Decimal("0")),
                 detail.get("igst_rt", Decimal("0")), detail.get("igst_amt", Decimal("0")),
                 "B", "", BILL_TYPE, supply_type, username[:10], l["particular"]],
            )

        amt_cols = {
            "amt_tf": totals["taxable_by_rate"][0], "amt5": totals["taxable_by_rate"][5],
            "amt12": totals["taxable_by_rate"][12], "amt18": totals["taxable_by_rate"][18],
            "amt28": totals["taxable_by_rate"][28],
        }
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
        adj_cols = {}
        for i in range(1, 3):
            a = adjustments[i - 1] if i <= len(adjustments) else None
            adj_cols[f"adj{i}"] = a["sign"] if a else ""
            adj_cols[f"adj_code{i}"] = a["code"] if a else ""
            adj_cols[f"adj_amt{i}"] = a["amount"] if a else Decimal("0")

        all_cols = {
            "div": DIV, "b_date": bill_date, "p_code": party_code, "ca_cr": "CR",
            "yn": "Y" if gst_enabled else "N", "gst_no": (payload.get("gst_no") or "").strip(),
            "cstat": supply_type, "ord_no": (payload.get("order_no") or "")[:15],
            "ord_dt": _date(payload.get("order_date")), "remk": (payload.get("remarks") or "")[:100],
            "amount": totals["amount"], "gst_amt": totals["gst_total"], "n_amount": totals["net_rounded"],
            "diff_amt": totals["diff"], "pmt_rcd": "N", "bill_type": BILL_TYPE, "uname": username[:10],
            "pack_ch": charges["pack_ch"], "commi": charges["commi"], "freight": charges["freight"],
            "insur": charges["insur"], "total": totals["assessable"], "gross": totals["gross"],
            **amt_cols, **gst_cols, **adj_cols,
        }
        cols = list(all_cols.keys())
        placeholders = ",".join(["%s"] * len(cols))
        values = [all_cols[c] for c in cols]
        if key:
            set_clause = ",".join(f"{c} = %s" for c in cols)
            _exec(f"UPDATE g_per SET {set_clause} WHERE bill_no = %s AND bill_type = %s",
                  values + [bill_no, BILL_TYPE])
        else:
            _exec(
                f"INSERT INTO g_per (bill_no, {', '.join(cols)}) VALUES (%s, {placeholders})",
                [bill_no] + values,
            )

        ProformaSpearpartExtra.objects.update_or_create(
            bill_no=bill_no,
            defaults={
                "pl_no": (payload.get("pl_no") or "")[:20],
                "pl_date": _date(payload.get("pl_date")),
                "others": (payload.get("others") or "")[:100],
            },
        )

    return {"bill_no": bill_no}


def delete_invoice(bill_no):
    _require_writes()
    with transaction.atomic(using="legacy"):
        if not _rows("SELECT bill_no FROM g_per WHERE bill_no = %s AND bill_type = %s", [bill_no, BILL_TYPE]):
            raise ProformaSpearpartError("This Performa Invoice Sparepart no longer exists.")
        _delete_legacy(bill_no)
        row = _rows("SELECT gp_no FROM inv_no")
        if row and str(int(_d(row[0]["gp_no"]))) == str(bill_no):
            _exec("UPDATE inv_no SET gp_no = %s", [int(bill_no) - 1])

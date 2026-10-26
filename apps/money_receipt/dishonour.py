"""Money Receipt > Cheque Dishonour (VFP "CHEQUE DISHONOUR" form).

Reverses a CHEQUE-mode Money Receipt (apps.money_receipt.services.save_receipt)
that bounced: un-clears every bill it had settled, restores the party's
advance to what it was before the receipt, reverses the ledger postings the
receipt made, and posts the bank charges the bank levied for the bounce.

Reuses apps.money_receipt.services's own already-confirmed tables/columns
(colh/col/bill/adv_fil/trans -- see that module's docstring) plus three
columns the pasted VFP source needs that services.py deliberately left
unused (see its own docstring): ``colh.dishonour``/``colh.ch_dt``/
``colh.b_charge`` (marks the receipt dishonoured, the date, and the bank's
charge) and ``col.chk_dis`` (marks a reversed allocation line -- kept, not
deleted, so the Money Receipt's own history stays visible; this is the one
deliberate difference from services.delete_receipt, which actually removes
the col rows it reverses).

Ledger codes: CASH_DISCOUNT_LEDGER_CODE ("D002") and the party's own code as
its ledger ("tcode = party_code") are services.py's already-confirmed
conventions, reused here unchanged. ``INTEREST_LEDGER_CODE`` ("1008") and
``BANK_CHARGE_CODE`` ("B001") are apps.creditor_outstanding.payment's own
already-confirmed "Interest Charges" / "Bank charges" codes (pintcode /
B001 in the VFP source), reused rather than guessed fresh. ``DEBTOR_GROUP_CODE``
("S001") is the VFP source's own hardcoded literal for the bank-charge-onto-
party leg (``tcode with 'S001'``) -- kept exactly as the legacy source has
it, the same call already made for apps.money_receipt.services's own
TDS_LEDGER_CODE literal.

Two assumptions flagged, not guessed, because the pasted source doesn't
resolve them from the fields this form (and its screenshot) actually expose:
  * ``tdate with thisform.tchqpdt.value`` (one single trans row, the
    "balance beyond previous advance" leg) -- no ``tchqpdt`` control appears
    anywhere else in the pasted source or the screenshot's field list. Every
    other trans row in this routine dates itself off the Cheque Dis. Date
    (``tchqdt``), so that's used here for this row too rather than inventing
    a second, unexposed date field.
  * The JV voucher number: the VFP source reads it from ``inv_no.l_v_no``,
    a global running counter apps.money_receipt doesn't otherwise use or
    reference anywhere (its own JV/CV numbering -- services._next_vno --
    already runs through the ``vno`` table's date-keyed counters for this
    exact app). Reusing that already-proven counter (keyed off the Cheque
    Dis. Date) avoids writing to an unconfirmed column for a number nothing
    else in this project reads back.
"""
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .services import CASH_DISCOUNT_LEDGER_CODE, DIV, _clean, _d, _date, _exec, _next_vno, _rows, writes_enabled

INTEREST_LEDGER_CODE = "1008"
BANK_CHARGE_CODE = "B001"
DEBTOR_GROUP_CODE = "S001"


class DishonourError(Exception):
    pass


def _require_writes():
    if not writes_enabled():
        raise DishonourError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def pending_cheques(party_code):
    """CHEQUE-mode receipts for this party not already marked dishonoured.
    colh has no mode column of its own (see services.get_receipt) -- a
    non-blank bank_code is this app's own established way of telling CHEQUE/
    RTGS apart from CASH, same as get_receipt() already relies on."""
    rows = _rows(
        "SELECT chq_no, chq_dt, slip_dt, amount, bank_code FROM colh "
        "WHERE p_code = %s AND bank_code <> '' AND (dishonour IS NULL OR dishonour <> 'Y') "
        "ORDER BY slip_dt DESC",
        [party_code],
    )
    return [{
        "chq_no": _clean(r["chq_no"]) or "", "chq_dt": r["chq_dt"].isoformat() if r["chq_dt"] else "",
        "slip_dt": r["slip_dt"].isoformat() if r["slip_dt"] else "", "amount": f"{_d(r['amount']):.2f}",
        "bank_code": _clean(r["bank_code"]) or "",
    } for r in rows]


def cheque_detail(party_code, chq_no):
    rows = _rows(
        "SELECT h.*, c.cname, c.cadd3, b.gdesc AS bank_name FROM colh h "
        "LEFT JOIN cust_mst c ON c.ccode = h.p_code LEFT JOIN gled_mst b ON b.gcode = h.bank_code "
        "WHERE h.p_code = %s AND h.chq_no = %s", [party_code, chq_no],
    )
    if not rows:
        return None
    h = rows[0]
    lines = _rows(
        "SELECT div, bill_no, b_date, b_amt, c_dis, int_amt, amount, bill_type FROM col "
        "WHERE nar = %s AND p_code = %s AND (chk_dis IS NULL OR chk_dis <> 'Y')", [_clean(h["chq_no"]), party_code],
    )
    return {
        "party_code": _clean(h["p_code"]), "party_name": _clean(h["cname"]) or "", "party_city": _clean(h["cadd3"]) or "",
        "bank_code": _clean(h["bank_code"]) or "", "bank_name": _clean(h["bank_name"]) or "",
        "chq_no": _clean(h["chq_no"]) or "", "chq_dt": h["chq_dt"].isoformat() if h["chq_dt"] else "",
        "slip_dt": h["slip_dt"].isoformat() if h["slip_dt"] else "",
        "amount": f"{_d(h['amount']):.2f}", "prev_adv": f"{_d(h['prev_adv']):.2f}",
        "total_amt": f"{_d(h['total_amt']):.2f}", "pend_adv": f"{_d(h['pend_adv']):.2f}",
        "already_dishonoured": _clean(h.get("dishonour")) == "Y",
        "lines": [
            {"div": _clean(l["div"]) or "", "bill_no": _clean(l["bill_no"]), "bill_type": _clean(l["bill_type"]) or "",
             "bill_date": l["b_date"].isoformat() if l["b_date"] else "",
             "inv_amount": f"{_d(l['b_amt']):.2f}", "cash_discount": f"{_d(l['c_dis']):.2f}",
             "interest_amt": f"{_d(l['int_amt']):.2f}", "amount_adjusted": f"{_d(l['amount']):.2f}"}
            for l in lines
        ],
    }


def save_dishonour(party_code, chq_no, ch_dt_str, bank_charges, username=""):
    _require_writes()
    party_code = (party_code or "").strip().upper()
    chq_no = (chq_no or "").strip()
    ch_dt = _date(ch_dt_str)
    if not ch_dt:
        raise DishonourError("Enter Cheque Dis. Date.")
    detail = cheque_detail(party_code, chq_no)
    if not detail or detail["already_dishonoured"]:
        raise DishonourError("This cheque entry no longer exists or is already marked dishonoured.")

    bank_charges = _d(bank_charges)
    lines = detail["lines"]
    mbalance = _d(detail["total_amt"])
    totcd = totint = Decimal("0")
    for l in lines:
        adj = _d(l["amount_adjusted"])
        if adj > 0:
            mbalance -= adj
            totcd += _d(l["cash_discount"])
            totint += _d(l["interest_amt"])

    username = (username or "")[:10]

    with transaction.atomic(using="legacy"):
        vou_no = str(_next_vno("CH", ch_dt))

        existing_adv = _rows("SELECT amount FROM adv_fil WHERE p_code = %s", [party_code])
        new_adv = _d(existing_adv[0]["amount"]) if existing_adv else Decimal("0")
        new_adv = new_adv - _d(detail["pend_adv"]) + _d(detail["prev_adv"])
        if new_adv <= 0:
            if existing_adv:
                _exec("DELETE FROM adv_fil WHERE p_code = %s", [party_code])
        elif existing_adv:
            _exec("UPDATE adv_fil SET amount = %s WHERE p_code = %s", [new_adv, party_code])
        else:
            _exec("INSERT INTO adv_fil (p_code, amount) VALUES (%s, %s)", [party_code, new_adv])

        _exec(
            "UPDATE colh SET dishonour = 'Y', b_charge = %s, ch_dt = %s WHERE p_code = %s AND chq_no = %s",
            [bank_charges, ch_dt, party_code, chq_no],
        )

        narration = ("Cheque Dishonour Chq.No. " + chq_no)[:60]

        def post(tdbcr, tcode, amount, tccode=""):
            if amount == 0:
                return
            _exec(
                "INSERT INTO trans (ttype, tdoc, tdate, tcode, tccode, tdbcr, tnar1, nar, tamt, div, uname, bill_type) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                ["JV", vou_no, ch_dt, tcode, tccode, tdbcr, narration, chq_no, amount, DIV, username, ""],
            )

        post("C", detail["bank_code"], _d(detail["amount"]))

        for l in lines:
            adj = _d(l["amount_adjusted"])
            if adj <= 0:
                continue
            cash_dis, interest = _d(l["cash_discount"]), _d(l["interest_amt"])
            _exec(
                "UPDATE bill SET amt_rcd = amt_rcd - %s, c_dis = c_dis - %s, int_amt = int_amt - %s, "
                "pmt_rcd = 'N', d_note1 = d_note1 + %s "
                "WHERE bill_no = %s AND bill_type = %s AND div = %s",
                [adj, cash_dis, interest, bank_charges, l["bill_no"], l["bill_type"], l["div"]],
            )
            _exec(
                "UPDATE col SET chk_dis = 'Y' WHERE nar = %s AND p_code = %s AND div = %s AND bill_no = %s",
                [chq_no, party_code, l["div"], l["bill_no"]],
            )
            if cash_dis > 0:
                post("C", CASH_DISCOUNT_LEDGER_CODE, cash_dis)
            if interest > 0:
                post("D", INTEREST_LEDGER_CODE, interest)
            post("D", party_code, adj, tccode=party_code)

        if mbalance - _d(detail["prev_adv"]) > 0:
            post("D", party_code, mbalance - _d(detail["prev_adv"]), tccode=party_code)
        if totcd > 0:
            post("D", party_code, totcd, tccode=party_code)
        if totint > 0:
            post("C", party_code, totint, tccode=party_code)
        if bank_charges > 0:
            post("C", BANK_CHARGE_CODE, bank_charges)
            post("D", DEBTOR_GROUP_CODE, bank_charges, tccode=party_code)

    return {"chq_no": chq_no, "vou_no": vou_no}


class DishonourView(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/dishonour.html"


@login_required
@require_GET
def dis_cheques(request):
    party = (request.GET.get("party_code") or "").strip().upper()
    if not party:
        return JsonResponse({"cheques": []})
    return JsonResponse({"cheques": pending_cheques(party)})


@login_required
@require_GET
def dis_detail(request):
    party = (request.GET.get("party_code") or "").strip().upper()
    chq_no = (request.GET.get("chq_no") or "").strip()
    data = cheque_detail(party, chq_no)
    if not data:
        return JsonResponse({"message": "Cheque entry not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def dis_save(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        result = save_dishonour(
            body.get("party_code"), body.get("chq_no"), body.get("ch_dt"), body.get("bank_charges"),
            username=request.user.get_username(),
        )
    except DishonourError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Cheque {result['chq_no']} marked dishonoured.", **result})

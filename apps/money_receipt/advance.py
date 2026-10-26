"""Money Receipt > Advance Adjustment (VFP "ADVANCE ADJUSTMENT" form).

Settles a customer's unadjusted advance (``adv_fil``) against their own
pending sale bills (``bill``, ``pmt_rcd='N'``) -- the same tables/columns
apps.money_receipt's own Money Receipt Entry screen already reads (see
services.pending_bills / services.previous_advance).

Each confirmed entry is recorded the way the VFP source's own
``cmdconfirm.Click`` (mflag=1) does -- one ``col`` row per adjusted bill and
one ``colh`` header row -- so it can be looked up and reversed by its own
ENTRY NO. later (DELETE), matching the original form's own ADD/DELETE/
CONFIRM/EXIT toolbar. Two deliberate substitutions versus the VFP source,
both already-established conventions elsewhere in this exact app rather than
guesses:
  * The VFP source links col->colh for this form via ``col.slip_no`` /
    ``seek`` on that index. apps.money_receipt.services's own confirmed
    column list for ``col`` (checked directly against the live DB -- see its
    docstring) has no ``slip_no`` column at all. This uses ``col.nar`` /
    ``colh.chq_no`` instead -- the identical linking convention
    services.save_receipt/get_receipt/delete_receipt already use for every
    other kind of ``colh`` row in this table.
  * ``col.chk_dis = 'A'`` and ``colh.dishonour = 'A'`` mark a row as created
    by this screen (as opposed to a real Money Receipt, or 'Y' for one
    apps.money_receipt.dishonour has since reversed) -- both columns are
    already live and read elsewhere in this app (dishonour.py's own
    cheque_detail query, collection.py's own totals), so this isn't a new
    unconfirmed column, just a new value in an existing one, exactly as the
    VFP source itself uses 'A' for this same purpose.

``colh.slip_no`` is left as ``'AD'`` (not the Entry No. -- that's
``colh.chq_no`` here, per the linking convention above) so
apps.money_receipt.collection's own CASH/CHEQUE split via ``colh.slip_no``
doesn't misread one of these rows as an actual cash receipt; collection.py
excludes ``chk_dis='A'`` rows from its CASH/CHEQUE totals for the same
reason (see its own docstring).
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .services import DIV, _clean, _d, _date, _exec, _rows, writes_enabled


class AdvanceError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _require_writes():
    if not writes_enabled():
        raise AdvanceError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def get_entry(party_code, ent_no):
    """An existing Advance Adjustment entry (for DELETE), identified the same
    way services.get_receipt identifies any other colh row: (p_code, chq_no)."""
    party_code = (party_code or "").strip().upper()
    ent_no = (ent_no or "").strip()
    header = _rows(
        "SELECT * FROM colh WHERE p_code = %s AND chq_no = %s AND dishonour = 'A'",
        [party_code, ent_no],
    )
    if not header:
        return None
    h = header[0]
    lines = _rows(
        "SELECT div, bill_no, bill_type, b_date, b_amt, c_dis, int_amt, amount FROM col "
        "WHERE nar = %s AND p_code = %s AND chk_dis = 'A'", [ent_no, party_code],
    )
    return {
        "ent_no": ent_no, "ent_dt": h["slip_dt"].isoformat() if h["slip_dt"] else "",
        "party_code": party_code, "prev_adv": f"{_d(h['prev_adv']):.2f}", "pend_adv": f"{_d(h['pend_adv']):.2f}",
        "lines": [
            {"div": _clean(l["div"]) or "", "bill_no": _clean(l["bill_no"]), "bill_type": _clean(l["bill_type"]) or "",
             "bill_date": l["b_date"].isoformat() if l["b_date"] else "", "bill_amount": f"{_d(l['b_amt']):.2f}",
             "cash_discount": f"{_d(l['c_dis']):.2f}", "interest_amt": f"{_d(l['int_amt']):.2f}",
             "adjusted": f"{_d(l['amount']):.2f}"}
            for l in lines
        ],
    }


def save_advance_adjustment(party_code, ent_no, ent_dt_str, adjustments, username=""):
    _require_writes()
    party_code = (party_code or "").strip().upper()
    ent_no = (ent_no or "").strip()
    ent_dt = _date(ent_dt_str)
    errors = {}
    if not party_code:
        errors["party_code"] = "Select a party first."
    if not ent_no:
        errors["ent_no"] = "Entry No. is required."
    if not ent_dt:
        errors["ent_dt"] = "Entry Date is required."
    if errors:
        raise AdvanceError("Fix the highlighted fields.", errors)
    if get_entry(party_code, ent_no):
        raise AdvanceError("This Entry No. already exists.", {"ent_no": "Already exists."})

    advance = services.previous_advance(party_code)
    total = sum((_d(a.get("adjusted")) for a in adjustments), Decimal("0"))
    if total <= 0:
        raise AdvanceError("Enter an amount to adjust.", {"amt_adj": "Enter an amount to adjust."})
    if total > advance:
        raise AdvanceError("Adjustment is more than the Pending Advance.")

    bills = {(b["bill_type"], b["div"], b["bill_no"]): b for b in services.pending_bills(party_code)}
    username = (username or "")[:10]

    with transaction.atomic(using="legacy"):
        for a in adjustments:
            amt = _d(a.get("adjusted"))
            if amt <= 0:
                continue
            key = (a.get("bill_type") or "", a.get("div") or "", a.get("bill_no") or "")
            bill = bills.get(key)
            if not bill:
                raise AdvanceError(f"Bill {a.get('bill_no')} is no longer pending.")
            if amt > _d(bill["balance_amt"]):
                raise AdvanceError(f"Adjustment for bill {a.get('bill_no')} is more than its balance.")
            cash_dis, interest = _d(a.get("cash_discount")), _d(a.get("interest_amt"))
            _exec(
                "UPDATE bill SET amt_rcd = amt_rcd + %s, c_dis = c_dis + %s, int_amt = int_amt + %s, uname = %s, "
                "pmt_rcd = CASE WHEN n_amount - (amt_rcd + %s) - c_note1 + d_note1 - (int_amt + %s) - (c_dis + %s) = 0 "
                "THEN 'Y' ELSE pmt_rcd END "
                "WHERE bill_no = %s AND bill_type = %s AND div = %s",
                [amt, cash_dis, interest, username, amt, interest, cash_dis, key[2], key[0], key[1]],
            )
            _exec(
                "INSERT INTO col (slip_dt, nar, p_code, div, bill_no, b_date, b_amt, c_dis, int_amt, amount, "
                "bill_type, uname, chk_dis) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [ent_dt, ent_no, party_code, key[1], key[2], _date(a.get("bill_date")), _d(bill["inv_amount"]),
                 cash_dis, interest, amt, key[0], username, "A"],
            )

        mbalance = advance - total
        _exec(
            "INSERT INTO colh (bank_code, slip_no, slip_dt, p_code, amount, prev_adv, total_amt, pend_adv, "
            "chq_no, chq_dt, vou_no, div, uname, dishonour) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ["", "AD", ent_dt, party_code, 0, advance, 0, mbalance, ent_no, None, "", DIV, username, "A"],
        )

        existing = _rows("SELECT amount FROM adv_fil WHERE p_code = %s", [party_code])
        if mbalance <= 0:
            if existing:
                _exec("DELETE FROM adv_fil WHERE p_code = %s", [party_code])
        else:
            if existing:
                _exec("UPDATE adv_fil SET amount = %s, uname = %s WHERE p_code = %s", [mbalance, username, party_code])
            else:
                _exec("INSERT INTO adv_fil (p_code, amount, uname) VALUES (%s, %s, %s)", [party_code, mbalance, username])

    return {"ent_no": ent_no, "adjusted": f"{total:.2f}", "advance_left": f"{max(mbalance, Decimal('0')):.2f}"}


def delete_advance_adjustment(party_code, ent_no, username=""):
    _require_writes()
    entry = get_entry(party_code, ent_no)
    if not entry:
        raise AdvanceError("This entry no longer exists.")
    party_code = entry["party_code"]
    username = (username or "")[:10]

    with transaction.atomic(using="legacy"):
        for l in entry["lines"]:
            _exec(
                "UPDATE bill SET amt_rcd = amt_rcd - %s, c_dis = c_dis - %s, int_amt = int_amt - %s, "
                "pmt_rcd = 'N', uname = %s WHERE bill_no = %s AND bill_type = %s AND div = %s",
                [_d(l["adjusted"]), _d(l["cash_discount"]), _d(l["interest_amt"]), username,
                 l["bill_no"], l["bill_type"], l["div"]],
            )
        _exec("DELETE FROM col WHERE nar = %s AND p_code = %s AND chk_dis = 'A'", [ent_no, party_code])
        _exec("DELETE FROM colh WHERE p_code = %s AND chq_no = %s AND dishonour = 'A'", [party_code, ent_no])

        existing = _rows("SELECT amount FROM adv_fil WHERE p_code = %s", [party_code])
        restored = _d(entry["prev_adv"]) - _d(entry["pend_adv"])
        if existing:
            _exec("UPDATE adv_fil SET amount = amount + %s, uname = %s WHERE p_code = %s", [restored, username, party_code])
        elif restored > 0:
            _exec("INSERT INTO adv_fil (p_code, amount, uname) VALUES (%s, %s, %s)", [party_code, restored, username])

    return {"ent_no": ent_no}


class AdvanceAdjustmentView(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/advance_adjustment.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"ent_dt": date.today().isoformat()}
        return context


@login_required
@require_GET
def adv_data(request):
    party = (request.GET.get("party_code") or "").strip().upper()
    if not party:
        return JsonResponse({"advance": "0.00", "bills": []})
    return JsonResponse({"advance": f"{services.previous_advance(party):.2f}", "bills": services.pending_bills(party)})


@login_required
@require_GET
def adv_entry(request):
    entry = get_entry(request.GET.get("party_code"), request.GET.get("ent_no"))
    if not entry:
        return JsonResponse({"message": "Entry not found."}, status=404)
    return JsonResponse(entry)


@login_required
@require_POST
def adv_save(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        result = save_advance_adjustment(
            body.get("party_code"), body.get("ent_no"), body.get("ent_dt"), body.get("lines") or [],
            username=request.user.get_username(),
        )
    except AdvanceError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Advance of {result['adjusted']} adjusted. Balance {result['advance_left']}.", **result})


@login_required
@require_POST
def adv_delete(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    try:
        result = delete_advance_adjustment(body.get("party_code"), body.get("ent_no"), username=request.user.get_username())
    except AdvanceError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Entry {result['ent_no']} deleted."})

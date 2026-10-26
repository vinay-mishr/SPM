"""Money Receipt > Cheque Master (VFP "CHEQUE MASTER" form).

A register of post-dated customer cheques held against a party (table
``chq_file``: p_code, chq_no, chq_dt, amount, mop, type), new to this app --
its columns come straight from the VFP source's own field list (no existing
Django model reads this table elsewhere). ``mop`` (1/2) is the VFP source's
own hardcoded bank choice ("SBI BANK"/"HDFC BANK" -- the dropdown has no
other options in the pasted source, so none are invented here either).
``type = 'S'`` is written on every row this screen creates, matching the
VFP source's own ``REPLACE TYPE WITH 'S'`` and its list's own ``TYPE='S'``
filter -- other values of ``type`` evidently belong to a different screen
that isn't part of this port.

The VFP source's own CONFIRM also opens a cheque-leaf print preview
(``REPORT FORM chqprn5/chqprn3 PREVIEW``, chosen by bank) -- those two
report layouts weren't supplied, so printing isn't implemented here. Add/
Modify/Delete/View all behave exactly as the legacy screen's own buttons
imply, confirmed against this pasted source, but if printing is needed later
it has to be designed fresh (and this app has no printer-leaf precedent to
copy from, unlike its Excel exports).
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from .services import _clean, _d, _date, _exec, _rows, writes_enabled

BANKS = {1: "SBI BANK", 2: "HDFC BANK"}
BANK_CODES = {v: k for k, v in BANKS.items()}


class ChequeMasterError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _require_writes():
    if not writes_enabled():
        raise ChequeMasterError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def list_cheques(start, end):
    rows = _rows(
        "SELECT f.chq_no, f.chq_dt, f.amount, f.mop, f.p_code, c.cname FROM chq_file f "
        "LEFT JOIN cust_mst c ON c.ccode = f.p_code "
        "WHERE f.type = 'S' AND f.chq_dt >= %s AND f.chq_dt <= %s ORDER BY f.chq_dt",
        [start, end],
    )
    out = []
    total = 0
    for r in rows:
        amount = _d(r["amount"])
        total += amount
        out.append({
            "chq_no": _clean(r["chq_no"]) or "", "chq_dt": r["chq_dt"].isoformat() if r["chq_dt"] else "",
            "party_name": _clean(r["cname"]) or "", "amount": f"{amount:.2f}",
            "bank": BANKS.get(int(_d(r["mop"])) if r["mop"] is not None else 0, ""),
        })
    return out, f"{total:.2f}"


def get_cheque(chq_no):
    rows = _rows(
        "SELECT f.chq_no, f.chq_dt, f.amount, f.mop, f.p_code, c.cname FROM chq_file f "
        "LEFT JOIN cust_mst c ON c.ccode = f.p_code WHERE f.type = 'S' AND f.chq_no = %s",
        [(chq_no or "").strip()],
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "chq_no": _clean(r["chq_no"]) or "", "chq_dt": r["chq_dt"].isoformat() if r["chq_dt"] else "",
        "party_code": _clean(r["p_code"]) or "", "party_name": _clean(r["cname"]) or "",
        "amount": f"{_d(r['amount']):.2f}",
        "bank": BANKS.get(int(_d(r["mop"])) if r["mop"] is not None else 0, ""),
    }


def save_cheque(mode, payload):
    _require_writes()
    chq_no = (payload.get("chq_no") or "").strip()
    chq_dt = _date(payload.get("chq_dt"))
    party_code = (payload.get("party_code") or "").strip().upper()
    bank = (payload.get("bank") or "").strip()
    amount = _d(payload.get("amount"))

    errors = {}
    if not chq_no:
        errors["chq_no"] = "Cheque No. is required."
    if not chq_dt:
        errors["chq_dt"] = "Cheque Date is required."
    if not party_code:
        errors["party_code"] = "Select a party."
    if bank not in BANK_CODES:
        errors["bank"] = "Select a bank."
    if amount <= 0:
        errors["amount"] = "Invalid Amount."
    if errors:
        raise ChequeMasterError("Fix the highlighted fields.", errors)

    mop = BANK_CODES[bank]
    with transaction.atomic(using="legacy"):
        if mode == "add":
            existing = get_cheque(chq_no)
            if existing:
                raise ChequeMasterError("This Cheque No. already exists.", {"chq_no": "Already exists."})
            _exec(
                "INSERT INTO chq_file (p_code, chq_no, chq_dt, amount, mop, type) VALUES (%s,%s,%s,%s,%s,%s)",
                [party_code, chq_no, chq_dt, amount, mop, "S"],
            )
        else:
            existing = get_cheque(chq_no)
            if not existing:
                raise ChequeMasterError("This Cheque No. no longer exists.")
            _exec(
                "UPDATE chq_file SET p_code = %s, chq_dt = %s, amount = %s, mop = %s "
                "WHERE type = 'S' AND chq_no = %s",
                [party_code, chq_dt, amount, mop, chq_no],
            )
    return {"chq_no": chq_no}


def delete_cheque(chq_no):
    _require_writes()
    chq_no = (chq_no or "").strip()
    existing = get_cheque(chq_no)
    if not existing:
        raise ChequeMasterError("This Cheque No. no longer exists.")
    _exec("DELETE FROM chq_file WHERE type = 'S' AND chq_no = %s", [chq_no])
    return {"chq_no": chq_no}


class ChequeMasterView(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/cheque_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


def _parse(value, default):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


@login_required
@require_GET
def cm_list(request):
    today = date.today()
    start = _parse(request.GET.get("start_date"), today)
    end = _parse(request.GET.get("end_date"), today)
    rows, total = list_cheques(start, end)
    return JsonResponse({"rows": rows, "total": total})


@login_required
@require_GET
def cm_detail(request):
    data = get_cheque(request.GET.get("chq_no"))
    if not data:
        return JsonResponse({"message": "Invalid Chq No."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def cm_save(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    mode = "modify" if body.get("mode") == "modify" else "add"
    try:
        result = save_cheque(mode, body)
    except ChequeMasterError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Cheque {result['chq_no']} saved.", **result})


@login_required
@require_POST
def cm_delete(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    try:
        result = delete_cheque(body.get("chq_no"))
    except ChequeMasterError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Cheque {result['chq_no']} deleted."})

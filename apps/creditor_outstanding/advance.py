"""Creditor Outstanding > Advance Adjustment (VFP advance adjustment form).

Settles a vendor's advance paid (adv_fil) against their pending bills (cr_out).
Each bill's adjustment may not exceed its balance, and the total may not exceed the advance.
"""
from decimal import Decimal

from django.db import connections, transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.db.models import Value
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from .models import AdvanceFile, CreditorBill
from .payment import balance_of, pending_bills

Q2 = Decimal("0.01")


class AdvanceError(Exception):
    pass


def advance_paid(party_code):
    rows = AdvanceFile.objects.filter(p_code=party_code).values_list("amount", flat=True)[:1]
    return Decimal(str(list(rows)[0] or 0)) if rows else Decimal("0")


def save_advance(party_code, adjustments, username=""):
    advance = advance_paid(party_code)
    total = sum((Decimal(str(a["adjusted"])) for a in adjustments), Decimal("0"))
    if total <= 0:
        raise AdvanceError("Enter an amount to adjust.")
    if total > advance:
        raise AdvanceError("Adjustment is more than the advance paid.")
    bills = {b["bill_no"]: b for b in pending_bills(party_code)}
    with transaction.atomic(using="legacy"):
        for a in adjustments:
            amt = Decimal(str(a["adjusted"]))
            if amt <= 0:
                continue
            bill = bills.get(a["bill_no"])
            if not bill:
                raise AdvanceError(f"Bill {a['bill_no']} is no longer pending.")
            if amt > Decimal(bill["balance"]):
                raise AdvanceError(f"Adjustment for bill {a['bill_no']} is more than its balance.")
            CreditorBill.objects.filter(p_code=party_code, inv_no=a["bill_no"]).update(
                pmt_rcd=Coalesce("pmt_rcd", Value(0)) + amt, uname=username[:10])
            current = list(CreditorBill.objects.filter(p_code=party_code, inv_no=a["bill_no"]).values(
                "amount", "pmt_rcd")[:1])[0]
            if Decimal(str(current["amount"] or 0)) - Decimal(str(current["pmt_rcd"] or 0)) == 0:
                CreditorBill.objects.filter(p_code=party_code, inv_no=a["bill_no"]).update(pmt_mad="Y")
        left = advance - total
        if left <= 0:
            with connections["legacy"].cursor() as cur:
                cur.execute("DELETE FROM adv_fil WHERE p_code = %s", [party_code])
        else:
            AdvanceFile.objects.filter(p_code=party_code).update(amount=left, uname=username[:10])
    return {"adjusted": f"{total:.2f}", "advance_left": f"{max(left, Decimal('0')):.2f}"}


class AdvanceAdjustmentView(LoginRequiredMixin, TemplateView):
    template_name = "creditor_outstanding/advance_adjustment.html"


@login_required
@require_GET
def adv_data(request):
    party = (request.GET.get("party_code") or "").strip().upper()
    if not party:
        return JsonResponse({"advance": "0.00", "bills": []})
    return JsonResponse({"advance": f"{advance_paid(party):.2f}", "bills": pending_bills(party)})


@login_required
@require_POST
def adv_save(request):
    import json
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        result = save_advance((body.get("party_code") or "").strip().upper(), body.get("lines") or [],
                              username=request.user.get_username())
    except AdvanceError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Advance of {result['adjusted']} adjusted. Balance {result['advance_left']}.", **result})

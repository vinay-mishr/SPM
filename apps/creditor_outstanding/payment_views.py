import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from apps.gl.models import Ledger
from apps.parties.models import Party

from . import payment

BANK_GROUP_CODE = "B0303"


class PaymentEntryView(LoginRequiredMixin, TemplateView):
    template_name = "creditor_outstanding/payment_entry.html"


@login_required
@require_GET
def pay_detail(request):
    data = payment.get_payment((request.GET.get("party_code") or "").strip().upper(),
                               (request.GET.get("chq_no") or "").strip())
    if not data:
        return JsonResponse({"message": "Payment not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_GET
def pay_list(request):
    return JsonResponse({"rows": payment.list_payments()})


@login_required
@require_GET
def pay_bills(request):
    party = (request.GET.get("party_code") or "").strip().upper()
    return JsonResponse({"bills": payment.pending_bills(party) if party else []})


@login_required
@require_GET
def pay_parties(request):
    term = (request.GET.get("q") or "").strip()
    qs = Party.objects.all()
    if term:
        qs = qs.filter(name__icontains=term) | qs.filter(party_code__istartswith=term)
    return JsonResponse({"parties": [{"code": c, "name": (n or "").strip(), "city": (ct or "").strip()}
                                     for c, n, ct in qs.order_by("name").values_list("party_code", "name", "city")[:200]]})


@login_required
@require_GET
def pay_banks(request):
    term = (request.GET.get("q") or "").strip()
    qs = Ledger.objects.filter(gl_type=BANK_GROUP_CODE)
    if term:
        qs = qs.filter(description__icontains=term) | qs.filter(ledger_code__istartswith=term)
    return JsonResponse({"banks": [{"code": c, "name": (d or "").strip()}
                                   for c, d in qs.order_by("description").values_list("ledger_code", "description")[:20]]})


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


@login_required
@require_POST
def pay_save(request):
    if not request.user.has_perm("creditor_outstanding.change_creditorbill") and not request.user.is_superuser:
        return JsonResponse({"message": "You don't have permission to post payments."}, status=403)
    body = _body(request)
    if body is None:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        result = payment.save_payment(body, username=request.user.get_username())
    except payment.PaymentError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Payment {result['chq_no']} posted as {result['voucher']}.", **result})


@login_required
@require_POST
def pay_delete(request):
    if not request.user.is_superuser:
        return JsonResponse({"message": "Only a superuser can delete a payment."}, status=403)
    body = _body(request) or {}
    try:
        payment.delete_payment(body.get("party_code", ""), (body.get("chq_no") or "").strip())
    except payment.PaymentError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": "Payment deleted and bills restored."})

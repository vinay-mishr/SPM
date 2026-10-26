import json
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import provider, services
from .models import EwayBill
from .provider import ProviderError
from .services import EwayBillError


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED


def _parse(value, default):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


class EwayBillView(LoginRequiredMixin, TemplateView):
    template_name = "eway_bill/eway_bill_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def eb_list(request):
    start = _parse(request.GET.get("start_date"), date.today())
    end = _parse(request.GET.get("end_date"), date.today())
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.list_eligible(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def eb_detail(request, bill_no):
    data = services.get_detail(bill_no)
    if not data:
        return JsonResponse({"message": "GST invoice not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def eb_save_transport(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change e-way bill details."}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    bill_no = (body.get("bill_no") or "").strip()
    if not bill_no:
        return JsonResponse({"message": "Bill number is required."}, status=400)
    try:
        e = services.save_transport_details(bill_no, body, request.user.get_username())
    except EwayBillError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    invoice = services.gi_services.get_invoice(bill_no)
    return JsonResponse({"message": "Transport details saved.", "eway": services._serialize(e, invoice)})


@login_required
@require_POST
def eb_generate(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to generate e-way bills."}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    bill_no = (body.get("bill_no") or "").strip()
    if not bill_no:
        return JsonResponse({"message": "Bill number is required."}, status=400)
    try:
        e = services.generate(bill_no, request.user.get_username())
    except EwayBillError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    invoice = services.gi_services.get_invoice(bill_no)
    return JsonResponse({"message": f"E-Way Bill {e.eway_bill_no} generated.", "eway": services._serialize(e, invoice)})


@login_required
@require_POST
def eb_token(request):
    """General provider auth token (not per-invoice, not per-search) -- reuses
    the cached token from provider.get_token() unless it's missing/expired,
    matching the provider's own documented single-auth-token workflow. Never
    returns a fabricated token: a missing config or provider failure surfaces
    the real error instead."""
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to request an auth token."}, status=403)
    try:
        token = provider.get_token()
    except ProviderError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    cached = provider.get_cached_token_record()
    return JsonResponse({
        "message": "Token ready.",
        "token": token,
        "provider": cached.provider if cached else "",
        "expires_at": cached.expires_at.isoformat() if cached else None,
    })


@login_required
@require_GET
def eb_json(request, bill_no):
    """The JSON action: shows the actual stored request/response for this bill
    (credentials already stripped at logging time by provider._redact) --
    never a fabricated or placeholder payload."""
    e = EwayBill.objects.filter(bill_no=bill_no).first()
    if not e:
        return JsonResponse({"message": "No e-way bill record for this invoice yet."}, status=404)
    return JsonResponse({
        "bill_no": e.bill_no,
        "status": e.status,
        "last_request": e.last_request,
        "last_response": e.last_response,
        "last_error": e.last_error,
        "logs": [
            {"action": log.action, "success": log.success, "created_at": log.created_at.isoformat(),
             "request": log.request_payload, "response": log.response_payload}
            for log in e.logs.all()[:20]
        ],
    })


class EwayBillPrintView(LoginRequiredMixin, TemplateView):
    template_name = "eway_bill/eway_bill_print.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bill_no = kwargs["bill_no"]
        e = EwayBill.objects.filter(bill_no=bill_no).first()
        invoice = services.gi_services.get_invoice(bill_no)
        if not invoice or not e or e.status != EwayBill.STATUS_GENERATED:
            raise Http404("No generated e-way bill for this invoice.")
        context["invoice"] = invoice
        context["eway"] = e
        context["brand_name"] = settings.BRAND["name"].upper()
        return context

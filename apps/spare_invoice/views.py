import json
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .services import SpareInvoiceError


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED


def _parse(value, default):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


class SpareInvoiceView(LoginRequiredMixin, TemplateView):
    template_name = "spare_invoice/spare_invoice_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def si_list(request):
    start = _parse(request.GET.get("start_date"), date.today())
    end = _parse(request.GET.get("end_date"), date.today())
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.list_invoices(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def si_next_no(request):
    return JsonResponse({"bill_no": str(services.next_no())})


@login_required
@require_GET
def si_detail(request, bill_no):
    data = services.get_invoice(bill_no, request.GET.get("div") or None, request.GET.get("vou_no") or None)
    if not data:
        return JsonResponse({"message": "Spare Part invoice not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_GET
def si_items(request):
    return JsonResponse({"items": services.search_items(request.GET.get("q", ""))})


@login_required
@require_GET
def si_parties(request):
    return JsonResponse({"parties": services.search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def si_item(request):
    data = services.item_detail(request.GET.get("code", ""))
    if not data:
        return JsonResponse({"message": "Part not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_GET
def si_party(request):
    data = services.party_detail(request.GET.get("code", ""))
    if not data:
        return JsonResponse({"message": "Party not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def si_save(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change Spare Part invoices."}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        if body.get("key"):
            result = services.save_invoice(
                body, key=body["key"], key_div=body.get("key_div"), key_vou_no=body.get("key_vou_no"),
                username=request.user.get_username(),
            )
        else:
            result = services.save_invoice(body, username=request.user.get_username())
    except SpareInvoiceError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Spare Part invoice {result['bill_no']} saved.", "bill_no": result["bill_no"]})


class SpareInvoicePrintView(LoginRequiredMixin, TemplateView):
    template_name = "spare_invoice/spare_invoice_print.html"

    def get_context_data(self, **kwargs):
        from apps.creditor_outstanding.remittance import amount_in_words

        context = super().get_context_data(**kwargs)
        data = services.print_data(
            kwargs["bill_no"], self.request.GET.get("div") or None, self.request.GET.get("vou_no") or None,
        )
        if not data:
            raise Http404("Spare Part invoice not found.")
        context["note"] = data
        context["brand_name"] = settings.BRAND["name"].upper()
        context["in_words"] = amount_in_words(data["net_amount"])
        context["bank"] = settings.QUOTATION_BANK
        context["preview"] = self.request.GET.get("preview") == "1"
        active_lines = [l for l in data["items"] if l["active"]]
        context["fill_rows"] = range(max(0, 12 - len(active_lines)))
        return context


@login_required
@require_POST
def si_delete(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change Spare Part invoices."}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    bill_no = (body.get("bill_no") or "").strip()
    try:
        services.delete_invoice(bill_no, (body.get("div") or "").strip(), (body.get("vou_no") or "").strip())
    except SpareInvoiceError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Spare Part invoice {bill_no} deleted."})

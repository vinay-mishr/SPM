import json
from datetime import date, datetime
from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
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
def si_ledgers(request):
    return JsonResponse({"ledgers": services.search_ledgers(request.GET.get("q", ""))})


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


_COPY_LABELS = {
    "Original For Recipient": "Original For Recipient",
    "Duplicate For Transporter": "Duplicate For Transporter",
    "Triplicate For Supplier": "Triplicate For Supplier",
}


def _print_context(bill_no, div=None, vou_no=None, copy_type=""):
    from apps.creditor_outstanding.remittance import amount_in_words

    data = services.print_data(bill_no, div, vou_no)
    if not data:
        return None
    active_lines = [l for l in data["items"] if l["active"]]
    return {
        "note": data,
        "brand_name": settings.BRAND["name"].upper(),
        "in_words": amount_in_words(data["net_amount"]),
        "bank": settings.QUOTATION_BANK,
        "fill_rows": range(max(0, 12 - len(active_lines))),
        "copy_label": _COPY_LABELS.get(copy_type, "Original For Recipient"),
    }


class SpareInvoicePrintView(LoginRequiredMixin, TemplateView):
    template_name = "spare_invoice/spare_invoice_print.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = _print_context(
            kwargs["bill_no"], self.request.GET.get("div") or None, self.request.GET.get("vou_no") or None,
            self.request.GET.get("copy", ""),
        )
        if not data:
            raise Http404("Spare Part invoice not found.")
        context.update(data)
        context["preview"] = self.request.GET.get("preview") == "1"
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


# --- PDF / WhatsApp share -----------------------------------------------------------------

def _pdf_static_link_callback(uri, rel):
    """xhtml2pdf doesn't fetch over HTTP -- resolves a STATIC_URL link to an
    on-disk path (same convention as apps.purchase_orders.views)."""
    from django.contrib.staticfiles import finders

    if uri.startswith(settings.STATIC_URL):
        path = finders.find(uri[len(settings.STATIC_URL):].split("?")[0])
        if path:
            return path
    return uri


def _render_invoice_pdf(request, bill_no, div=None, vou_no=None, copy_type=""):
    """The actual PDF bytes for one Spare Part invoice (xhtml2pdf) -- a
    separate, plain table-based template (spare_invoice_pdf.html), not
    spare_invoice_print.html: that page relies on flexbox/CSS grid this
    renderer doesn't support. Shared by both the public share-link PDF and
    the in-app "Print PDF" button, same convention as apps.purchase_orders."""
    from xhtml2pdf import pisa

    context = _print_context(bill_no, div, vou_no, copy_type)
    if not context:
        return None
    html = render(request, "spare_invoice/spare_invoice_pdf.html", context).content.decode("utf-8")
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, link_callback=_pdf_static_link_callback)
    if result.err:
        return None
    return buffer.getvalue()


@login_required
@require_GET
def si_pdf(request, bill_no):
    """"Print PDF" from inside the app -- the same real PDF the public
    WhatsApp share link serves, just reached directly by someone already
    logged in, with no share token or link-generation step needed."""
    pdf_bytes = _render_invoice_pdf(
        request, bill_no, request.GET.get("div") or None, request.GET.get("vou_no") or None, request.GET.get("copy", ""),
    )
    if pdf_bytes is None:
        raise Http404("Spare Part invoice not found.")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Spare_Invoice_{bill_no}.pdf"'
    return response


@login_required
@require_POST
def si_share_link(request, bill_no):
    """Creates (or reuses) a public, no-login link to this invoice's actual
    PDF, for the WhatsApp "Send on WhatsApp" flow."""
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    div = (body.get("div") or "").strip() or None
    vou_no = (body.get("vou_no") or "").strip() or None
    token = services.get_share_token(bill_no, div, vou_no)
    if not token:
        return JsonResponse({"message": "Spare Part invoice not found."}, status=404)
    return JsonResponse({
        "url": request.build_absolute_uri(reverse("spare_invoice_share_pdf", args=[token])),
        "preview_url": request.build_absolute_uri(reverse("spare_invoice_share_view", args=[token])),
    })


@require_GET
def si_share_view(request, token):
    """Public page a share link's token points to -- no login required."""
    bill_no, div, vou_no = services.get_bill_by_share_token(token)
    if not bill_no:
        return render(request, "spare_invoice/spare_invoice_share_invalid.html", status=404)
    context = _print_context(bill_no, div, vou_no)
    if not context:
        return render(request, "spare_invoice/spare_invoice_share_invalid.html", status=404)
    context["preview"] = True
    context["public"] = True
    context["pdf_url"] = request.build_absolute_uri(reverse("spare_invoice_share_pdf", args=[token]))
    return render(request, "spare_invoice/spare_invoice_print.html", context)


@require_GET
def si_share_pdf(request, token):
    """The actual downloadable PDF a share link's token points to -- no login required."""
    bill_no, div, vou_no = services.get_bill_by_share_token(token)
    if not bill_no:
        raise Http404("This link isn't available.")
    pdf_bytes = _render_invoice_pdf(request, bill_no, div, vou_no)
    if pdf_bytes is None:
        raise Http404("This link isn't available.")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Spare_Invoice_{bill_no}.pdf"'
    return response

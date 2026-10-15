"""Returnable Challan views -- Challan Entry and the Party Wise Pending Challan report."""
import json
from datetime import date, datetime
from io import BytesIO

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services


def _parse(raw, default):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED and user.has_perm(services.CHALLAN_PERMISSION)


def _forbidden():
    return JsonResponse({"message": "You don't have permission to change challans."}, status=403)


class ChallanEntryView(LoginRequiredMixin, TemplateView):
    template_name = "returnable_challan/challan_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {
            "rows": services.list_challans(today, today), "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


@login_required
@require_GET
def challan_pending_for_party(request):
    """For apps.spare_invoice's ADD CHALLAN picker -- this party's challans that
    still have at least one not-yet-billed line."""
    return JsonResponse({"challans": services.list_pending_for_party(request.GET.get("party_code", ""))})


@login_required
@require_GET
def challan_pending_items(request, chl_no):
    """Not-yet-billed items of one challan, for apps.spare_invoice to import --
    requires the caller's own selected party_code to match, so one party's
    challan can never be pulled into another party's invoice."""
    items = services.get_pending_items(chl_no, request.GET.get("party_code", ""))
    if items is None:
        return JsonResponse({"message": "Challan not found for this party."}, status=404)
    if not items:
        return JsonResponse({"message": "This challan has no items left to import -- already fully billed."}, status=400)
    return JsonResponse({"items": items})


@login_required
@require_GET
def challan_parties(request):
    """Party lookup for the PARTY field -- all parties (challans go to any
    customer, not just Sundry Creditors, unlike the Purchase Order endpoint
    this screen's own party search was pointed at before)."""
    from apps.parties.models import Party

    term = (request.GET.get("q") or "").strip()
    qs = Party.objects.all()
    if term:
        qs = qs.filter(name__icontains=term) | qs.filter(party_code__istartswith=term)
    return JsonResponse({"parties": [{"code": c, "name": (n or "").strip(), "city": (ct or "").strip(), "mobile": (m or "").strip()}
                                     for c, n, ct, m in qs.order_by("name").values_list("party_code", "name", "city", "mobile_1")[:200]]})


@login_required
@require_GET
def challan_list(request):
    today = date.today()
    start = _parse(request.GET.get("start_date"), today)
    end = _parse(request.GET.get("end_date"), today)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.list_challans(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def challan_next_no(request):
    return JsonResponse({"chl_no": services.next_challan_no()})


@login_required
@require_GET
def challan_detail(request, chl_no):
    data = services.get_challan(chl_no)
    if not data:
        return JsonResponse({"message": "Challan not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def challan_reauthenticate(request):
    try:
        payload = json.loads(request.body or "{}")
    except ValueError:
        payload = {}
    user = authenticate(request, username=request.user.get_username(), password=payload.get("password") or "")
    if user is None:
        return JsonResponse({"ok": False, "message": "Invalid password."}, status=403)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def challan_save(request):
    if not _can_edit(request.user):
        return _forbidden()
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        result = services.save_challan(payload, key=payload.get("key") or None,
                                       username=request.user.get_username()[:10])
    except services.ChallanError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Challan {result['chl_no']} saved.", "chl_no": result["chl_no"]})


@login_required
@require_POST
def challan_delete(request):
    if not _can_edit(request.user):
        return _forbidden()
    chl_no = request.POST.get("chl_no", "")
    try:
        services.delete_challan(chl_no)
    except services.ChallanError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Challan {chl_no} deleted."})


class ChallanPrintView(LoginRequiredMixin, TemplateView):
    template_name = "returnable_challan/challan_print.html"

    def get_context_data(self, **kwargs):
        from apps.creditor_outstanding.remittance import amount_in_words

        context = super().get_context_data(**kwargs)
        data = services.get_challan(kwargs["chl_no"])
        if not data:
            raise Http404("Challan not found.")
        context["challan"] = data
        context["brand_name"] = settings.BRAND["name"].upper()
        context["in_words"] = amount_in_words(data["net_amount"])
        # "View" opens this without the auto-print dialog, for a clean preview.
        context["preview"] = self.request.GET.get("preview") == "1"
        context["copy_type"] = self.request.GET.get("copy", "")
        return context


def _pdf_static_link_callback(uri, rel):
    """xhtml2pdf doesn't fetch over HTTP -- resolves a STATIC_URL link (the
    logo) to an on-disk path, same helper as the Purchase Order / MRN PDF
    exports (each app keeps its own copy since static files aren't shared
    across Django apps)."""
    from django.contrib.staticfiles import finders

    if uri.startswith(settings.STATIC_URL):
        path = finders.find(uri[len(settings.STATIC_URL):].split("?")[0])
        if path:
            return path
    return uri


def _render_challan_pdf(request, challan, copy_type=""):
    """The actual PDF bytes for one challan (xhtml2pdf) -- not the HTML print
    page: that page relies on flexbox this renderer doesn't support, so this
    uses a separate, simpler, table-based template with the same data
    (challan_pdf.html). Shared by both the public share-link PDF and the
    in-app "Print PDF" button, so there's exactly one PDF-generation path."""
    from xhtml2pdf import pisa

    from apps.creditor_outstanding.remittance import amount_in_words

    html = render(request, "returnable_challan/challan_pdf.html", {
        "challan": challan, "copy_type": copy_type, "in_words": amount_in_words(challan["net_amount"]),
    }).content.decode("utf-8")
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, link_callback=_pdf_static_link_callback)
    if result.err:
        return None
    return buffer.getvalue()


@login_required
@require_GET
def challan_pdf(request, chl_no):
    """"Print PDF" from inside the app -- the same real PDF the public
    WhatsApp share link serves, just reached directly by someone already
    logged in, with no share token or link-generation step needed."""
    data = services.get_challan(chl_no)
    if not data:
        raise Http404("Challan not found.")
    pdf_bytes = _render_challan_pdf(request, data, request.GET.get("copy", ""))
    if pdf_bytes is None:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Challan_{chl_no}.pdf"'
    return response


@login_required
@require_POST
def challan_share_link(request, chl_no):
    """Creates (or reuses) a public, no-login link to this challan's actual
    PDF, for the WhatsApp "Send on WhatsApp" flow -- same convention as the
    Purchase Order module's order_share_link."""
    token = services.get_challan_share_token(chl_no)
    if not token:
        return JsonResponse({"message": "Challan not found."}, status=404)
    return JsonResponse({
        "url": request.build_absolute_uri(reverse("challan_share_pdf", args=[token])),
        "preview_url": request.build_absolute_uri(reverse("challan_share_view", args=[token])),
    })


@require_GET
def challan_share_view(request, token):
    """Public page a share link's token points to -- no login required. Shows
    the challan and a Download PDF button; an invalid, expired or revoked
    token gets a plain "not available" page instead of the challan."""
    chl_no = services.get_challan_by_share_token(token)
    data = services.get_challan(chl_no) if chl_no else None
    if not data:
        return render(request, "returnable_challan/challan_share_invalid.html", status=404)
    from apps.creditor_outstanding.remittance import amount_in_words

    return render(request, "returnable_challan/challan_print.html", {
        "challan": data, "brand_name": settings.BRAND["name"].upper(),
        "in_words": amount_in_words(data["amount"]), "preview": True, "public": True,
        "pdf_url": request.build_absolute_uri(reverse("challan_share_pdf", args=[token])),
    })


@require_GET
def challan_share_pdf(request, token):
    """The actual downloadable PDF a share link's token points to -- no login
    required. An invalid, expired or revoked token is a 404, not a PDF."""
    chl_no = services.get_challan_by_share_token(token)
    data = services.get_challan(chl_no) if chl_no else None
    if not data:
        raise Http404("This link isn't available.")
    pdf_bytes = _render_challan_pdf(request, data)
    if pdf_bytes is None:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Challan_{chl_no}.pdf"'
    return response


class PendingChallanReportView(LoginRequiredMixin, TemplateView):
    template_name = "returnable_challan/pending_challan_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.replace(day=1).isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def pending_challan_data(request):
    party = request.GET.get("party_code", "").strip()
    start = _parse(request.GET.get("start_date"), date.today().replace(day=1))
    end = _parse(request.GET.get("end_date"), date.today())
    if not party:
        return JsonResponse({"message": "Select a party first."}, status=400)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse(services.pending_challan_report(party, start, end))


@login_required
@require_GET
def pending_challan_export(request):
    from . import exports

    party = request.GET.get("party_code", "").strip()
    start = _parse(request.GET.get("start_date"), date.today().replace(day=1))
    end = _parse(request.GET.get("end_date"), date.today())
    if not party or start > end:
        return JsonResponse({"message": "Select a party and a valid date range."}, status=400)
    data = services.pending_challan_report(party, start, end)
    body = exports.build_pending_challan_workbook(data, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(body, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="Pending_Challan.xlsx"'
    return response

import json
from datetime import date
from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import exports, services

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."

PO_PRINT_TERMS = [
    "Supply should be made as per the agreed delivery schedule.",
    "The supplier will be responsible for damage or loss of material in transit.",
    "Kindly mention our P.O. No. and part number on the invoice.",
    "Payment shall be made as per the agreed payment terms.",
    "All materials in the purchase order should be delivered as agreed.",
]


def _can_edit(user):
    return services.writes_enabled() and user.has_perm(services.PERMISSION)


def _forbidden(user):
    if not services.writes_enabled():
        return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
    return JsonResponse({"message": "You don't have permission to change purchase orders."}, status=403)


def _key(request):
    parts = (request.POST.get("key") or "").split("|")
    return tuple(parts) if len(parts) == 2 else None


def _json_key(payload):
    parts = (payload.get("key") or "").split("|")
    return tuple(parts) if len(parts) == 2 else None


class PurchaseOrderMasterView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/purchase_order_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        context.update(
            can_edit=can_edit,
            initial_data={"orders": services.list_orders(), "can_edit": can_edit},
        )
        return context


@login_required
@require_GET
def order_list(request):
    return JsonResponse({"orders": services.list_orders()})


@login_required
@require_GET
def order_detail(request, div, po_no):
    order = services.get_order(div, po_no)
    if not order:
        return JsonResponse({"message": "Purchase order not found."}, status=404)
    return JsonResponse(order)


@login_required
@require_GET
def party_search(request):
    return JsonResponse({"parties": services.search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def part_search(request):
    return JsonResponse({"parts": services.search_parts(request.GET.get("q", ""))})


@login_required
@require_GET
def part_reference(request):
    ref = services.part_reference(request.GET.get("code", ""), request.GET.get("vendor", ""))
    if not ref:
        return JsonResponse({"message": "Part not found."}, status=404)
    ref["last_rate"] = services.last_rate(request.GET.get("code", ""))
    return JsonResponse(ref)


@login_required
@require_GET
def previous_info(request, part_code):
    return JsonResponse({"part_code": part_code, "history": services.previous_info(part_code)})


@login_required
@require_POST
def order_save(request):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        div, po_no = services.save(
            payload.get("div"), payload.get("po_no"), payload.get("party_code"),
            payload.get("order_date"), payload.get("lines"),
            request.user.get_username(), key=_json_key(payload),
            remarks=payload.get("remarks"), payment=payload.get("payment"), note=payload.get("note"),
        )
    except services.PurchaseOrderError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({
        "message": f"Purchase order {div}/{po_no} saved.",
        "key": f"{div}|{po_no}",
        "orders": services.list_orders(),
    })


@login_required
@require_GET
def order_print(request, div, po_no):
    from apps.parties.models import Party

    order = services.get_order(div, po_no)
    if not order:
        raise Http404("Purchase order not found.")
    party = Party.objects.filter(party_code=order["party_code"]).first()
    # Blank rows (same cells, same column dividers, no horizontal rule between
    # them) so the grid's vertical lines carry on below the real items instead
    # of stopping dead -- same idea as the legacy PO1 report's fixed-height band.
    fill_rows = range(max(0, 20 - len(order["lines"])))
    return render(request, "purchase_orders/purchase_order_print.html", {
        "order": order, "party": party, "terms": PO_PRINT_TERMS, "fill_rows": fill_rows,
        # "Print View" opens this without the auto-print dialog, for a clean preview.
        "preview": request.GET.get("preview") == "1",
        "copy_type": request.GET.get("copy", ""),
    })


@login_required
@require_POST
def order_share_link(request, div, po_no):
    """Creates (or reuses) a public, no-login link to this PO's actual PDF, for
    the WhatsApp "Send on WhatsApp" flow. The link's domain is whatever this
    request actually arrived on (never hardcoded), so it's correct in
    development and wherever this is actually deployed -- Django's own
    ALLOWED_HOSTS already guarantees that's a real, intended host, not
    something attacker-controlled."""
    token = services.get_po_share_token(div, po_no)
    if not token:
        return JsonResponse({"message": "Purchase order not found."}, status=404)
    return JsonResponse({
        "url": request.build_absolute_uri(reverse("po_share_pdf", args=[token])),
        "preview_url": request.build_absolute_uri(reverse("po_share_view", args=[token])),
    })


@require_GET
def order_share_view(request, token):
    """Public page a share link's token points to -- no login required. Shows
    the Purchase Order and a Download PDF button; an invalid, expired or
    revoked token gets a plain "not available" page instead of the PO."""
    from apps.parties.models import Party

    order = services.get_order_by_share_token(token)
    if not order:
        return render(request, "purchase_orders/purchase_order_share_invalid.html", status=404)
    party = Party.objects.filter(party_code=order["party_code"]).first()
    fill_rows = range(max(0, 20 - len(order["lines"])))
    return render(request, "purchase_orders/purchase_order_print.html", {
        "order": order, "party": party, "terms": PO_PRINT_TERMS, "fill_rows": fill_rows,
        "preview": True, "public": True, "pdf_url": request.build_absolute_uri(reverse("po_share_pdf", args=[token])),
    })


def _render_order_pdf(request, order, copy_type=""):
    """The actual PDF bytes for one PO (xhtml2pdf) -- not the HTML print page:
    that page relies on flexbox/CSS grid this renderer doesn't support, so
    this uses a separate, simpler, table-based template with the same data
    and calculations (purchase_order_pdf.html) rather than reusing that
    stylesheet. Shared by both the public share-link PDF and the in-app
    "Print PDF" button, so there's exactly one PDF-generation path."""
    from xhtml2pdf import pisa

    from apps.parties.models import Party

    party = Party.objects.filter(party_code=order["party_code"]).first()
    html = render(request, "purchase_orders/purchase_order_pdf.html", {
        "order": order, "party": party, "terms": PO_PRINT_TERMS, "copy_type": copy_type,
    }).content.decode("utf-8")

    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, link_callback=_pdf_static_link_callback)
    if result.err:
        return None
    return buffer.getvalue()


@login_required
@require_GET
def order_pdf(request, div, po_no):
    """"Print PDF" from inside the app -- the same real PDF the public
    WhatsApp share link serves, just reached directly by someone already
    logged in, with no share token or link-generation step needed."""
    order = services.get_order(div, po_no)
    if not order:
        raise Http404("Purchase order not found.")
    pdf_bytes = _render_order_pdf(request, order, request.GET.get("copy", ""))
    if pdf_bytes is None:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Purchase_Order_{po_no}.pdf"'
    return response


@require_GET
def order_share_pdf(request, token):
    """The actual downloadable PDF a share link's token points to -- no login
    required. An invalid, expired or revoked token is a 404, not a PDF."""
    order = services.get_order_by_share_token(token)
    if not order:
        raise Http404("This link isn't available.")
    pdf_bytes = _render_order_pdf(request, order)
    if pdf_bytes is None:
        return HttpResponse("Could not generate the PDF.", status=500)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Purchase_Order_{order["po_no"]}.pdf"'
    return response


def _pdf_static_link_callback(uri, rel):
    """xhtml2pdf doesn't fetch over HTTP -- resolves a STATIC_URL link (none
    used by purchase_order_pdf.html today, but kept for if one ever is) to an
    on-disk path the same way the project's other PDF export already does."""
    from django.contrib.staticfiles import finders

    if uri.startswith(settings.STATIC_URL):
        path = finders.find(uri[len(settings.STATIC_URL):].split("?")[0])
        if path:
            return path
    return uri


@login_required
@require_POST
def order_delete(request):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    key = _key(request)
    if not key:
        return JsonResponse({"message": "Select a purchase order first."}, status=400)
    try:
        services.delete_order(*key)
    except services.PurchaseOrderError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Purchase order {key[0]}/{key[1]} deleted.", "orders": services.list_orders()})


# --- Party Wise Pending Purchase Order report ------------------------------------------------

def _parse_date(request, param, default=None):
    raw = request.GET.get(param, "")
    try:
        y, m, d = raw.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return default if default is not None else date.today()


def _parse_as_on(request):
    return _parse_date(request, "as_on")


class PendingOrderReportView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/pending_order_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today().isoformat()
        context["initial_data"] = {"groups": services.pending_orders(date.today()), "as_on": today}
        return context


@login_required
@require_GET
def pending_orders_data(request):
    as_on = _parse_as_on(request)
    party_code = request.GET.get("party_code", "").strip()
    return JsonResponse({"groups": services.pending_orders(as_on, party_code or None), "as_on": as_on.isoformat()})


def _filter_pending_groups(groups, query):
    """Same match as the report's quick search box (party name/code, city, item
    code/name, order no) -- so Excel exports exactly what's on screen when a
    search is active, instead of always exporting everything."""
    query = (query or "").strip().lower()
    if not query:
        return groups
    filtered = []
    for group in groups:
        haystack_prefix = " ".join(str(group.get(k) or "") for k in ("party_name", "party_code", "city")).lower()
        lines = [
            line for line in group["lines"]
            if query in (haystack_prefix + " " + " ".join(
                str(line.get(k) or "") for k in ("item_code", "item_name", "ord_no")
            ).lower())
        ]
        if lines:
            filtered.append({**group, "lines": lines})
    return filtered


@login_required
@require_GET
def pending_orders_export(request):
    as_on = _parse_as_on(request)
    party_code = request.GET.get("party_code", "").strip()
    groups = services.pending_orders(as_on, party_code or None)
    groups = _filter_pending_groups(groups, request.GET.get("q", ""))
    data = exports.build_workbook(groups, settings.BRAND["name"].upper(), as_on)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="party_wise_pending_po.xlsx"'
    return response


# --- Party Wise Pending P.O. Despatch report --------------------------------------------------

class PendingDespatchReportView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/pending_despatch_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "groups": services.pending_despatch(today, today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(), "run_date": today.isoformat(),
        }
        return context


def _despatch_params(request):
    today = date.today()
    start = _parse_date(request, "start_date", today)
    end = _parse_date(request, "end_date", today)
    run = _parse_date(request, "run_date", today)
    item_code = request.GET.get("item_code", "").strip()
    return start, end, run, (item_code or None)


@login_required
@require_GET
def pending_despatch_data(request):
    start, end, run, item_code = _despatch_params(request)
    groups = services.pending_despatch(start, end, run, item_code=item_code)
    return JsonResponse({
        "groups": groups, "start_date": start.isoformat(), "end_date": end.isoformat(), "run_date": run.isoformat(),
    })


@login_required
@require_GET
def pending_despatch_export(request):
    start, end, run, item_code = _despatch_params(request)
    groups = services.pending_despatch(start, end, run, item_code=item_code)
    data = exports.build_despatch_workbook(groups, settings.BRAND["name"].upper(), run)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="party_wise_pending_po_despatch.xlsx"'
    return response


# --- Item Wise Pending Purchase Order report ---------------------------------------------------

class ItemWisePendingReportView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/item_wise_pending_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today().isoformat()
        context["initial_data"] = {"groups": services.item_wise_pending(date.today()), "run_date": today}
        return context


@login_required
@require_GET
def item_wise_pending_data(request):
    run_date = _parse_date(request, "run_date")
    part_code = request.GET.get("part_code", "").strip()
    return JsonResponse({
        "groups": services.item_wise_pending(run_date, part_code or None), "run_date": run_date.isoformat(),
    })


@login_required
@require_GET
def item_wise_pending_export(request):
    run_date = _parse_date(request, "run_date")
    part_code = request.GET.get("part_code", "").strip()
    groups = services.item_wise_pending(run_date, part_code or None)
    data = exports.build_item_wise_workbook(groups, settings.BRAND["name"].upper(), run_date)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="item_wise_pending_po.xlsx"'
    return response


# --- Monthly Order Report ---------------------------------------------------------------------

def _current_month_range():
    import calendar
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last_day)


def _monthly_order_report_params(request):
    default_start, default_end = _current_month_range()
    start = _parse_date(request, "start_date", default_start)
    end = _parse_date(request, "end_date", default_end)
    return start, end


class MonthlyOrderReportView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/monthly_order_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end = _current_month_range()
        context["initial_data"] = {
            "rows": services.monthly_order_report(start, end),
            "start_date": start.isoformat(), "end_date": end.isoformat(),
        }
        return context


@login_required
@require_GET
def monthly_order_report_data(request):
    start, end = _monthly_order_report_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.monthly_order_report(start, end)
    return JsonResponse({"rows": rows, "start_date": start.isoformat(), "end_date": end.isoformat()})


@login_required
@require_GET
def monthly_order_report_export(request):
    start, end = _monthly_order_report_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.monthly_order_report(start, end)
    data = exports.build_monthly_order_report_workbook(rows, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    filename = f"Monthly_Order_Report_{start.strftime('%d-%m-%Y')}_to_{end.strftime('%d-%m-%Y')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
def monthly_order_report_print(request):
    start, end = _monthly_order_report_params(request)
    rows = services.monthly_order_report(start, end) if start <= end else []
    for line in rows:
        line["ord_date"] = _dmy(line["ord_date"])
        line["despatch_date"] = _dmy(line["despatch_date"])
    return render(request, "purchase_orders/monthly_order_report_print.html", {
        "rows": rows, "start_date": start, "end_date": end,
    })


# --- Monthly Purchase Report ---------------------------------------------------------------

class MonthlyPurchaseReportView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/monthly_purchase_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "rows": services.monthly_purchase_report(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


def _monthly_purchase_params(request):
    today = date.today()
    start = _parse_date(request, "start_date", today)
    end = _parse_date(request, "end_date", today)
    return start, end


@login_required
@require_GET
def monthly_purchase_report_data(request):
    start, end = _monthly_purchase_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.monthly_purchase_report(start, end)
    return JsonResponse({"rows": rows, "start_date": start.isoformat(), "end_date": end.isoformat()})


@login_required
@require_GET
def monthly_purchase_report_export(request):
    start, end = _monthly_purchase_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.monthly_purchase_report(start, end)
    data = exports.build_monthly_purchase_workbook(rows, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="monthly_purchase_report.xlsx"'
    return response


# --- Item Wise Rate List report --------------------------------------------------------------

class ItemWiseRateListView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/item_wise_rate_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "groups": services.item_wise_rate_list(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


def _item_wise_rate_params(request):
    today = date.today()
    start = _parse_date(request, "start_date", today)
    end = _parse_date(request, "end_date", today)
    part_code = request.GET.get("part_code", "").strip()
    return start, end, (part_code or None)


@login_required
@require_GET
def item_wise_rate_list_data(request):
    start, end, part_code = _item_wise_rate_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    groups = services.item_wise_rate_list(start, end, part_code)
    return JsonResponse({"groups": groups, "start_date": start.isoformat(), "end_date": end.isoformat()})


@login_required
@require_GET
def item_wise_rate_list_export(request):
    start, end, part_code = _item_wise_rate_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    groups = services.item_wise_rate_list(start, end, part_code)
    data = exports.build_item_wise_rate_workbook(groups, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="item_wise_rate_list.xlsx"'
    return response


def _dmy(iso):
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


@login_required
@require_GET
def item_wise_rate_list_print(request):
    start, end, part_code = _item_wise_rate_params(request)
    groups = services.item_wise_rate_list(start, end, part_code)
    for group in groups:
        for line in group["lines"]:
            line["bill_date"] = _dmy(line["bill_date"])
    return render(request, "purchase_orders/item_wise_rate_list_print.html", {
        "groups": groups, "start_date": start, "end_date": end,
    })


# --- Party Wise Rate List report --------------------------------------------------------------

class PartyWiseRateListView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/party_wise_rate_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "groups": services.party_wise_rate_list(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


def _party_wise_rate_params(request):
    today = date.today()
    start = _parse_date(request, "start_date", today)
    end = _parse_date(request, "end_date", today)
    party_code = request.GET.get("party_code", "").strip()
    return start, end, (party_code or None)


@login_required
@require_GET
def party_wise_rate_list_data(request):
    start, end, party_code = _party_wise_rate_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    groups = services.party_wise_rate_list(start, end, party_code)
    return JsonResponse({"groups": groups, "start_date": start.isoformat(), "end_date": end.isoformat()})


@login_required
@require_GET
def party_wise_rate_list_export(request):
    start, end, party_code = _party_wise_rate_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    groups = services.party_wise_rate_list(start, end, party_code)
    data = exports.build_party_wise_rate_workbook(groups, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="party_wise_rate_list.xlsx"'
    return response


@login_required
@require_GET
def party_wise_rate_list_print(request):
    start, end, party_code = _party_wise_rate_params(request)
    groups = services.party_wise_rate_list(start, end, party_code)
    for group in groups:
        for line in group["lines"]:
            line["bill_date"] = _dmy(line["bill_date"])
    return render(request, "purchase_orders/party_wise_rate_list_print.html", {
        "groups": groups, "start_date": start, "end_date": end,
    })


# --- Party Pending Order Letter ----------------------------------------------------------------

class PartyPendingOrderLetterView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/party_pending_order_letter.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"run_date": date.today().isoformat()}
        return context


@login_required
@require_GET
def party_pending_order_letter_data(request):
    party_code = request.GET.get("party_code", "").strip()
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    run_date = _parse_date(request, "run_date")
    result = services.party_pending_order_letter(party_code, run_date)
    if not result:
        return JsonResponse({"message": "Party not found."}, status=404)
    result["run_date"] = run_date.isoformat()
    return JsonResponse(result)


@login_required
@require_GET
def party_pending_order_letter_export(request):
    party_code = request.GET.get("party_code", "").strip()
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    run_date = _parse_date(request, "run_date")
    result = services.party_pending_order_letter(party_code, run_date)
    if not result:
        return JsonResponse({"message": "Party not found."}, status=404)
    data = exports.build_pending_order_letter_workbook(
        result["party"], result["lines"], settings.BRAND["name"].upper(), run_date,
    )
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="party_pending_order_letter.xlsx"'
    return response


@login_required
@require_GET
def party_pending_order_letter_print(request):
    party_code = request.GET.get("party_code", "").strip()
    run_date = _parse_date(request, "run_date")
    result = services.party_pending_order_letter(party_code, run_date) if party_code else None
    if result:
        for line in result["lines"]:
            line["ord_date"] = _dmy(line["ord_date"])
            line["despatch_date"] = _dmy(line["despatch_date"])
    return render(request, "purchase_orders/party_pending_order_letter_print.html", {
        "result": result, "run_date": run_date,
        # "Print View" opens this without the auto-print dialog, for a clean preview.
        "preview": request.GET.get("preview") == "1",
        "copy_type": request.GET.get("copy", ""),
    })


@login_required
@require_GET
def party_pending_order_letter_pdf(request):
    """"Print PDF" for the reminder letter itself (it can cover several POs at
    once, so there's no single PO to generate a per-PO PDF for) -- a real PDF
    (xhtml2pdf), reusing the same service call and a plain, separate,
    table-based template (see purchase_order_pdf.html for why)."""
    party_code = request.GET.get("party_code", "").strip()
    run_date = _parse_date(request, "run_date")
    if not party_code:
        return HttpResponse("Select a party first.", status=400)
    result = services.party_pending_order_letter(party_code, run_date)
    if not result:
        raise Http404("Party not found.")
    for line in result["lines"]:
        line["ord_date"] = _dmy(line["ord_date"])
        line["despatch_date"] = _dmy(line["despatch_date"])
    html = render(request, "purchase_orders/party_pending_order_letter_pdf.html", {
        "result": result, "run_date": run_date, "copy_type": request.GET.get("copy", ""),
    }).content.decode("utf-8")

    from xhtml2pdf import pisa
    buffer = BytesIO()
    pdf_result = pisa.CreatePDF(html, dest=buffer, link_callback=_pdf_static_link_callback)
    if pdf_result.err:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Pending_PO_Reminder_{party_code}.pdf"'
    return response


def _render_pending_letter_pdf(request, result, run_date, copy_type=""):
    """The actual PDF bytes for one party's reminder letter -- shared by both
    the public share-link PDF and the in-app "Print PDF" button, same pattern
    as _render_order_pdf for the Purchase Order screen."""
    for line in result["lines"]:
        line["ord_date"] = _dmy(line["ord_date"])
        line["despatch_date"] = _dmy(line["despatch_date"])
    html = render(request, "purchase_orders/party_pending_order_letter_pdf.html", {
        "result": result, "run_date": run_date, "copy_type": copy_type,
    }).content.decode("utf-8")

    from xhtml2pdf import pisa
    buffer = BytesIO()
    pdf_result = pisa.CreatePDF(html, dest=buffer, link_callback=_pdf_static_link_callback)
    if pdf_result.err:
        return None
    return buffer.getvalue()


@login_required
@require_POST
def pending_order_letter_share_link(request):
    """Creates (or reuses) a public, no-login link to one party's Pending PO
    Reminder letter PDF, for the WhatsApp "Send on WhatsApp" flow -- same
    convention as order_share_link for a single PO."""
    body = json.loads(request.body or "{}")
    party_code = (body.get("party_code") or "").strip()
    try:
        y, m, d = (body.get("run_date") or "").split("-")
        run_date = date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        run_date = date.today()
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    token = services.get_pending_letter_share_token(party_code, run_date)
    if not token:
        return JsonResponse({"message": "Party not found."}, status=404)
    return JsonResponse({
        "url": request.build_absolute_uri(reverse("pending_order_letter_share_pdf", args=[token])),
        "preview_url": request.build_absolute_uri(reverse("pending_order_letter_share_view", args=[token])),
    })


@require_GET
def pending_order_letter_share_view(request, token):
    """Public page a reminder share link's token points to -- no login
    required. An invalid, expired or revoked token gets a plain "not
    available" page instead of the letter."""
    party_code, run_date = services.get_pending_letter_by_share_token(token)
    if not party_code:
        return render(request, "purchase_orders/purchase_order_share_invalid.html", status=404)
    result = services.party_pending_order_letter(party_code, run_date)
    if not result:
        return render(request, "purchase_orders/purchase_order_share_invalid.html", status=404)
    for line in result["lines"]:
        line["ord_date"] = _dmy(line["ord_date"])
        line["despatch_date"] = _dmy(line["despatch_date"])
    return render(request, "purchase_orders/party_pending_order_letter_print.html", {
        "result": result, "run_date": run_date, "preview": True, "public": True,
        "pdf_url": request.build_absolute_uri(reverse("pending_order_letter_share_pdf", args=[token])),
    })


@require_GET
def pending_order_letter_share_pdf(request, token):
    """The actual downloadable reminder PDF a share link's token points to --
    no login required. An invalid, expired or revoked token is a 404."""
    party_code, run_date = services.get_pending_letter_by_share_token(token)
    if not party_code:
        raise Http404("This link isn't available.")
    result = services.party_pending_order_letter(party_code, run_date)
    if not result:
        raise Http404("This link isn't available.")
    pdf_bytes = _render_pending_letter_pdf(request, result, run_date)
    if pdf_bytes is None:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Pending_PO_Reminder_{party_code}.pdf"'
    return response


# --- Itemwise Party List report -----------------------------------------------------------

class ItemwisePartyListView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/itemwise_party_list.html"


@login_required
@require_GET
def itemwise_party_list_data(request):
    part_code = request.GET.get("part_code", "").strip()
    if not part_code:
        return JsonResponse({"message": "Select an item first."}, status=400)
    result = services.itemwise_party_list(part_code)
    if not result:
        return JsonResponse({"message": "Item not found."}, status=404)
    return JsonResponse(result)


@login_required
@require_GET
def itemwise_party_list_export(request):
    part_code = request.GET.get("part_code", "").strip()
    if not part_code:
        return JsonResponse({"message": "Select an item first."}, status=400)
    result = services.itemwise_party_list(part_code)
    if not result:
        return JsonResponse({"message": "Item not found."}, status=404)
    data = exports.build_itemwise_party_list_workbook(result["part"], result["rows"], settings.BRAND["name"].upper())
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="itemwise_party_list.xlsx"'
    return response


@login_required
@require_GET
def itemwise_party_list_print(request):
    part_code = request.GET.get("part_code", "").strip()
    result = services.itemwise_party_list(part_code) if part_code else None
    return render(request, "purchase_orders/itemwise_party_list_print.html", {"result": result})


# --- Party Wise Item List report -----------------------------------------------------------

class PartyWiseItemListView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/party_wise_item_list.html"


@login_required
@require_GET
def party_wise_item_list_data(request):
    party_code = request.GET.get("party_code", "").strip()
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    result = services.party_wise_item_list(party_code)
    if not result:
        return JsonResponse({"message": "Party not found."}, status=404)
    return JsonResponse(result)


@login_required
@require_GET
def party_wise_item_list_export(request):
    party_code = request.GET.get("party_code", "").strip()
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    result = services.party_wise_item_list(party_code)
    if not result:
        return JsonResponse({"message": "Party not found."}, status=404)
    data = exports.build_party_wise_item_list_workbook(result["party"], result["rows"], settings.BRAND["name"].upper())
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="party_wise_item_list.xlsx"'
    return response


# --- Pending Purchase Order Adjustment -------------------------------------------------------

class PurchaseOrderAdjustmentView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/purchase_order_adjustment.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        context.update(can_edit=can_edit, initial_data={"can_edit": can_edit, "run_date": date.today().isoformat()})
        return context


@login_required
@require_GET
def po_adjustment_data(request):
    party_code = request.GET.get("party_code", "").strip()
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    result = services.pending_po_adjustment(party_code)
    if not result:
        return JsonResponse({"message": "Party not found."}, status=404)
    return JsonResponse(result)


@login_required
@require_POST
def po_adjustment_save(request):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        result = services.save_po_adjustments(payload.get("party_code"), payload.get("rows"))
    except services.PurchaseOrderAdjustmentError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    message = f"{result['updated']} order line(s) adjusted."
    if result["skipped"]:
        message += f" {len(result['skipped'])} row(s) were skipped (already adjusted or no longer pending)."
    return JsonResponse({"message": message, "updated": result["updated"], "skipped": result["skipped"]})


# --- Party-Wise Purchase Order Adjustment report ----------------------------------------------

class PartyWisePoAdjustmentReportView(LoginRequiredMixin, TemplateView):
    template_name = "purchase_orders/party_wise_po_adjustment.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "groups": services.party_wise_po_adjustment(today), "run_date": today.isoformat(),
        }
        return context


@login_required
@require_GET
def party_wise_po_adjustment_data(request):
    run_date = _parse_date(request, "run_date")
    party_code = request.GET.get("party_code", "").strip()
    groups = services.party_wise_po_adjustment(run_date, party_code or None)
    return JsonResponse({"groups": groups, "run_date": run_date.isoformat()})


@login_required
@require_GET
def party_wise_po_adjustment_export(request):
    run_date = _parse_date(request, "run_date")
    party_code = request.GET.get("party_code", "").strip()
    groups = services.party_wise_po_adjustment(run_date, party_code or None)
    data = exports.build_po_adjustment_workbook(groups, settings.BRAND["name"].upper(), run_date)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="party_wise_po_adjustment.xlsx"'
    return response

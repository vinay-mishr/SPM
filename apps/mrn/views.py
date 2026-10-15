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

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."


def _can_edit(user):
    return services.writes_enabled() and user.has_perm(services.PERMISSION)


def _forbidden():
    if not services.writes_enabled():
        return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
    return JsonResponse({"message": "You don't have permission to change MRNs."}, status=403)


def _parse_date(raw, default=None):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


class MrnEntryView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/mrn_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        today = date.today().isoformat()
        context.update(
            can_edit=can_edit,
            initial_data={
                "rows": services.list_mrns(today, today),
                "start_date": today, "end_date": today,
                "can_edit": can_edit,
            },
        )
        return context


@login_required
@require_GET
def mrn_list(request):
    today = date.today().isoformat()
    start = _parse_date(request.GET.get("start_date"), default=date.today())
    end = _parse_date(request.GET.get("end_date"), default=date.today())
    return JsonResponse({"rows": services.list_mrns(start, end)})


@login_required
@require_GET
def mrn_next_no(request):
    try:
        return JsonResponse({"mrn_no": services.next_mrn_no()})
    except services.MrnError as exc:
        return JsonResponse({"message": str(exc)}, status=400)


@login_required
@require_GET
def mrn_detail(request, div, mrn_no):
    order = services.get_mrn(div, mrn_no)
    if not order:
        return JsonResponse({"message": "MRN not found."}, status=404)
    return JsonResponse(order)


@login_required
@require_GET
def pending_po_lookup(request):
    party_code = (request.GET.get("party_code") or "").strip().upper()
    part_code = (request.GET.get("part_code") or "").strip().upper()
    if not party_code or not part_code:
        return JsonResponse({"pending": None})
    return JsonResponse({"pending": services.pending_po_for(party_code, part_code)})


@login_required
@require_POST
def reauthenticate(request):
    """Re-checks the CURRENT user's own account password (never a shared
    stored one) before Modify/Delete/Close, same intent as the legacy
    screen's password prompt -- but server-validated, per-user, and never
    exposing any stored password value to the browser."""
    import json
    try:
        payload = json.loads(request.body or "{}")
    except ValueError:
        payload = {}
    password = payload.get("password") or ""
    user = authenticate(request, username=request.user.get_username(), password=password)
    if user is None:
        return JsonResponse({"ok": False, "message": "Invalid password."}, status=403)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def mrn_save(request):
    if not _can_edit(request.user):
        return _forbidden()
    import json
    try:
        payload = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"message": "Malformed request."}, status=400)
    key = None
    if payload.get("key"):
        parts = payload["key"].split("|")
        if len(parts) == 2:
            key = tuple(parts)
    try:
        result = services.save_mrn(
            div=payload.get("div", "SP"),
            party_code=payload.get("party_code", ""),
            mrn_date=_parse_date(payload.get("mrn_date")),
            items=payload.get("items") or [],
            key=key,
            bill_no=payload.get("bill_no", ""),
            bill_date=_parse_date(payload.get("bill_date")),
            challan_no=payload.get("challan_no", ""),
            challan_date=_parse_date(payload.get("challan_date")),
            transport=payload.get("transport", ""),
            gr_no=payload.get("gr_no", ""),
            gr_date=_parse_date(payload.get("gr_date")),
            remarks=payload.get("remarks", ""),
            check_po=payload.get("check_po", "Y"),
            other_charge_1=payload.get("other_charge_1", 0),
            other_charge_2=payload.get("other_charge_2", 0),
            username=request.user.get_username(),
        )
    except services.MrnError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({
        "message": f"MRN {result['div']}/{result['mrn_no']} saved.",
        "key": f"{result['div']}|{result['mrn_no']}",
    })


@login_required
@require_POST
def mrn_close(request):
    if not _can_edit(request.user):
        return _forbidden()
    div, mrn_no = request.POST.get("div", ""), request.POST.get("mrn_no", "")
    try:
        services.close_mrn(div, mrn_no, username=request.user.get_username())
    except services.MrnError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"MRN {div}/{mrn_no} closed."})


@login_required
@require_POST
def mrn_delete(request):
    if not _can_edit(request.user):
        return _forbidden()
    div, mrn_no = request.POST.get("div", ""), request.POST.get("mrn_no", "")
    try:
        services.delete_mrn(div, mrn_no, username=request.user.get_username())
    except services.MrnError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"MRN {div}/{mrn_no} deleted."})


def _dmy(iso):
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{d}-{m}-{y}"


def _format_order_dates(order):
    order["mrn_date"] = _dmy(order["mrn_date"])
    order["challan_date"] = _dmy(order["challan_date"])
    order["bill_date"] = _dmy(order["bill_date"])
    order["gr_date"] = _dmy(order["gr_date"])
    return order


@login_required
@require_GET
def mrn_print(request, div, mrn_no):
    order = services.get_mrn(div, mrn_no)
    if not order:
        raise Http404("MRN not found.")
    _format_order_dates(order)
    return render(request, "mrn/mrn_print.html", {
        "order": order, "preview": request.GET.get("preview") == "1",
    })


def _pdf_static_link_callback(uri, rel):
    """xhtml2pdf doesn't fetch over HTTP -- resolves a STATIC_URL link (the logo)
    to an on-disk path, same helper as the Purchase Order PDF export."""
    from django.contrib.staticfiles import finders

    if uri.startswith(settings.STATIC_URL):
        path = finders.find(uri[len(settings.STATIC_URL):].split("?")[0])
        if path:
            return path
    return uri


def _render_mrn_pdf(request, order):
    """The actual PDF bytes for one MRN (xhtml2pdf) -- a separate, plain
    table-based template (mrn_pdf.html), not mrn_print.html: that page relies
    on flexbox this renderer doesn't support. Shared by both the public share-
    link PDF and the in-app "Print PDF" button, so there's exactly one PDF-
    generation path, same convention as the Purchase Order module."""
    from xhtml2pdf import pisa

    html = render(request, "mrn/mrn_pdf.html", {"order": order}).content.decode("utf-8")
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, link_callback=_pdf_static_link_callback)
    if result.err:
        return None
    return buffer.getvalue()


@login_required
@require_GET
def mrn_pdf(request, div, mrn_no):
    """"Print PDF" from inside the app -- the same real PDF the public
    WhatsApp share link serves, just reached directly by someone already
    logged in, with no share token or link-generation step needed."""
    order = services.get_mrn(div, mrn_no)
    if not order:
        raise Http404("MRN not found.")
    _format_order_dates(order)
    pdf_bytes = _render_mrn_pdf(request, order)
    if pdf_bytes is None:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="MRN_{mrn_no}.pdf"'
    return response


@login_required
@require_POST
def mrn_share_link(request, div, mrn_no):
    """Creates (or reuses) a public, no-login link to this MRN's actual PDF,
    for the WhatsApp "Send on WhatsApp" flow -- same convention as the
    Purchase Order module's order_share_link."""
    token = services.get_mrn_share_token(div, mrn_no)
    if not token:
        return JsonResponse({"message": "MRN not found."}, status=404)
    return JsonResponse({
        "url": request.build_absolute_uri(reverse("mrn_share_pdf", args=[token])),
        "preview_url": request.build_absolute_uri(reverse("mrn_share_view", args=[token])),
    })


@require_GET
def mrn_share_view(request, token):
    """Public page a share link's token points to -- no login required. Shows
    the MRN and a Download PDF button; an invalid, expired or revoked token
    gets a plain "not available" page instead of the MRN."""
    div, mrn_no = services.get_mrn_by_share_token(token)
    if not div:
        return render(request, "mrn/mrn_share_invalid.html", status=404)
    order = services.get_mrn(div, mrn_no)
    if not order:
        return render(request, "mrn/mrn_share_invalid.html", status=404)
    _format_order_dates(order)
    return render(request, "mrn/mrn_print.html", {
        "order": order, "preview": True, "public": True,
        "pdf_url": request.build_absolute_uri(reverse("mrn_share_pdf", args=[token])),
    })


@require_GET
def mrn_share_pdf(request, token):
    """The actual downloadable PDF a share link's token points to -- no login
    required. An invalid, expired or revoked token is a 404."""
    div, mrn_no = services.get_mrn_by_share_token(token)
    if not div:
        raise Http404("This link isn't available.")
    order = services.get_mrn(div, mrn_no)
    if not order:
        raise Http404("This link isn't available.")
    _format_order_dates(order)
    pdf_bytes = _render_mrn_pdf(request, order)
    if pdf_bytes is None:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="MRN_{mrn_no}.pdf"'
    return response


# --- Pending MRN report ------------------------------------------------------------

class PendingMrnReportView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/pending_mrn_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "rows": services.pending_mrns(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


def _pending_mrn_params(request):
    today = date.today()
    start = _parse_date(request.GET.get("start_date"), today)
    end = _parse_date(request.GET.get("end_date"), today)
    return start, end


@login_required
@require_GET
def pending_mrn_data(request):
    start, end = _pending_mrn_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.pending_mrns(start, end)
    return JsonResponse({"rows": rows, "start_date": start.isoformat(), "end_date": end.isoformat()})


@login_required
@require_GET
def pending_mrn_export(request):
    from . import exports

    start, end = _pending_mrn_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.pending_mrns(start, end)
    data = exports.build_pending_mrn_workbook(rows, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="pending_mrn_report.xlsx"'
    return response


# --- Current Stock report ------------------------------------------------------------

class CurrentStockReportView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/current_stock_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "rows": services.current_stock_report(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


def _stock_params(request):
    today = date.today()
    return _parse_date(request.GET.get("start_date"), today), _parse_date(request.GET.get("end_date"), today)


@login_required
@require_GET
def current_stock_data(request):
    start, end = _stock_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.current_stock_report(start, end)})


@login_required
@require_GET
def current_stock_export(request):
    from django.http import HttpResponse
    from . import exports

    start, end = _stock_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.current_stock_report(start, end)
    data = exports.build_current_stock_workbook(rows, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="current_stock.xlsx"'
    return response


# --- Stock Statement ----------------------------------------------------------------

class StockStatementView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/stock_statement.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "rows": services.stock_statement(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


@login_required
@require_GET
def stock_statement_data(request):
    start, end = _stock_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.stock_statement(start, end)})


@login_required
@require_GET
def stock_statement_export(request):
    from django.http import HttpResponse
    from . import exports

    start, end = _stock_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.stock_statement(start, end)
    data = exports.build_stock_statement_workbook(rows, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Stock_Statement_{start.strftime("%d-%m-%Y")}_to_{end.strftime("%d-%m-%Y")}.xlsx"'
    return response


# --- Raw Material Stock Ledger ----------------------------------------------------------

class StockLedgerView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/stock_ledger.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "rows": services.stock_ledger(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(), "mode": "all", "grade": "",
        }
        return context


def _ledger_params(request):
    start, end = _stock_params(request)
    mode = request.GET.get("mode", "all")
    grade = request.GET.get("grade", "").strip() if mode == "single" else None
    return start, end, grade


@login_required
@require_GET
def stock_ledger_data(request):
    start, end, grade = _ledger_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    if grade is not None and not grade:
        return JsonResponse({"message": "Enter a grade for a single-grade ledger."}, status=400)
    return JsonResponse({"rows": services.stock_ledger(start, end, grade)})


@login_required
@require_GET
def stock_ledger_export(request):
    from django.http import HttpResponse
    from . import exports

    start, end, grade = _ledger_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    if grade is not None and not grade:
        return JsonResponse({"message": "Enter a grade for a single-grade ledger."}, status=400)
    rows = services.stock_ledger(start, end, grade)
    data = exports.build_stock_ledger_workbook(rows, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Stock_Ledger_{start.strftime("%d-%m-%Y")}_to_{end.strftime("%d-%m-%Y")}.xlsx"'
    return response


@login_required
@require_GET
def stock_ledger_print(request):
    start, end, grade = _ledger_params(request)
    rows = services.stock_ledger(start, end, grade) if start <= end else []
    return render(request, "mrn/stock_ledger_print.html", {
        "rows": rows, "start_date": start, "end_date": end,
        "preview": request.GET.get("preview") == "1",
    })


# --- Item-wise Month-wise Sale -----------------------------------------------------------

class ItemMonthwiseSaleView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/item_monthwise_sale.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fy = _fy_start(date.today())
        context["months"] = MONTH_LABELS
        context["initial_data"] = {
            "rows": services.item_monthwise_sale(fy), "fy_from": fy.isoformat(), "months": MONTH_LABELS,
        }
        return context


def _fy_start(day):
    return date(day.year if day.month >= 4 else day.year - 1, 4, 1)


MONTH_LABELS = ["April", "May", "June", "July", "August", "September", "October", "November", "December",
                "January", "February", "March"]


@login_required
@require_GET
def item_monthwise_sale_data(request):
    fy = _parse_date(request.GET.get("fy_from"), None) or _fy_start(date.today())
    return JsonResponse({"rows": services.item_monthwise_sale(fy), "fy_from": fy.isoformat(), "months": MONTH_LABELS})


@login_required
@require_GET
def item_monthwise_sale_export(request):
    from django.http import HttpResponse
    from . import exports

    fy = _parse_date(request.GET.get("fy_from"), None) or _fy_start(date.today())
    rows = services.item_monthwise_sale(fy)
    data = exports.build_item_monthwise_sale_workbook(rows, settings.BRAND["name"].upper(), fy)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Itemwise_Monthwise_Sale_FY{fy.year}.xlsx"'
    return response


# --- Critical Shortage ----------------------------------------------------------------

class CriticalShortageView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/critical_shortage.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fy = _fy_start(date.today())
        today = date.today()
        context["initial_data"] = {
            "rows": services.critical_shortage(fy, today, 30, 30),
            "start_date": fy.isoformat(), "end_date": today.isoformat(), "days1": 30, "days2": 30,
        }
        return context


def _shortage_params(request):
    today = date.today()
    start = _parse_date(request.GET.get("start_date"), _fy_start(today))
    end = _parse_date(request.GET.get("end_date"), today)
    try:
        last_days = int(request.GET.get("days1", 30))
        cur_days = int(request.GET.get("days2", 30))
    except ValueError:
        last_days, cur_days = 30, 30
    return start, end, last_days, cur_days


@login_required
@require_GET
def critical_shortage_data(request):
    start, end, last_days, cur_days = _shortage_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.critical_shortage(start, end, last_days, cur_days)})


@login_required
@require_GET
def critical_shortage_export(request):
    from django.http import HttpResponse
    from . import exports

    start, end, last_days, cur_days = _shortage_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.critical_shortage(start, end, last_days, cur_days)
    data = exports.build_critical_shortage_workbook(rows, settings.BRAND["name"].upper(), start, end, last_days, cur_days)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="Critical_Shortage.xlsx"'
    return response


# --- Crisis Shortage ----------------------------------------------------------------

CRISIS_CATEGORIES = {"all", "routine", "subassembly", "workshop"}


class CrisisShortageView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/crisis_shortage.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fy = _fy_start(date.today())
        today = date.today()
        context["initial_data"] = {
            "rows": services.crisis_shortage(fy, today, 7, "all"),
            "start_date": fy.isoformat(), "end_date": today.isoformat(), "days": 7, "category": "all",
        }
        return context


def _crisis_params(request):
    today = date.today()
    start = _parse_date(request.GET.get("start_date"), _fy_start(today))
    end = _parse_date(request.GET.get("end_date"), today)
    try:
        days = int(request.GET.get("days", 7))
    except ValueError:
        days = 7
    category = request.GET.get("category", "all")
    if category not in CRISIS_CATEGORIES:
        category = "all"
    return start, end, days, category


@login_required
@require_GET
def crisis_shortage_data(request):
    start, end, days, category = _crisis_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.crisis_shortage(start, end, days, category)})


@login_required
@require_GET
def crisis_shortage_export(request):
    from django.http import HttpResponse
    from . import exports

    start, end, days, category = _crisis_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.crisis_shortage(start, end, days, category)
    data = exports.build_crisis_shortage_workbook(rows, settings.BRAND["name"].upper(), end, days, category)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="Crisis_Shortage.xlsx"'
    return response

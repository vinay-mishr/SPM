import json
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services


def _parse(raw, default):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED and user.has_perm(services.PERMISSION)


def _forbidden():
    return JsonResponse({"message": "You don't have permission to change job cards."}, status=403)


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


def _error(exc):
    return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)


class JobCardEntryView(LoginRequiredMixin, TemplateView):
    template_name = "job_card/job_card_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {"start_date": today.replace(day=1).isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def job_list(request):
    today = date.today()
    start = _parse(request.GET.get("start_date"), today.replace(day=1))
    end = _parse(request.GET.get("end_date"), today)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.list_jobs(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def job_next_no(request):
    return JsonResponse({"job_no": services.next_job_no()})


@login_required
@require_GET
def job_detail(request, job_no):
    data = services.get_job(job_no)
    if not data:
        return JsonResponse({"message": "Job card not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_GET
def job_items(request):
    return JsonResponse({"items": services.search_items(request.GET.get("q", ""))})


@login_required
@require_POST
def job_reauthenticate(request):
    payload = _body(request) or {}
    user = authenticate(request, username=request.user.get_username(), password=payload.get("password") or "")
    if user is None:
        return JsonResponse({"ok": False, "message": "Invalid password."}, status=403)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def job_save(request):
    if not _can_edit(request.user):
        return _forbidden()
    payload = _body(request)
    if payload is None:
        return JsonResponse({"message": "Invalid request."}, status=400)
    username = request.user.get_username()
    try:
        if payload.get("key"):
            result = services.save_modify(payload, username=username)
        else:
            result = services.save_add(payload, username=username)
    except services.JobError as exc:
        return _error(exc)
    return JsonResponse({"message": f"Job card {result['job_no']} saved.", "job_no": result["job_no"]})


@login_required
@require_POST
def job_receive(request):
    if not _can_edit(request.user):
        return _forbidden()
    payload = _body(request) or {}
    try:
        result = services.receive_job(payload.get("job_no", ""), payload.get("qty"), username=request.user.get_username())
    except services.JobError as exc:
        return _error(exc)
    return JsonResponse({"message": f"Received against job card {result['job_no']}.", "job_no": result["job_no"]})


@login_required
@require_POST
def job_close(request):
    if not _can_edit(request.user):
        return _forbidden()
    payload = _body(request) or {}
    try:
        result = services.close_job(payload.get("job_no", ""), payload, username=request.user.get_username())
    except services.JobError as exc:
        return _error(exc)
    return JsonResponse({"message": f"Job card {result['job_no']} closed.", "job_no": result["job_no"]})


@login_required
@require_POST
def job_delete(request):
    if not _can_edit(request.user):
        return _forbidden()
    payload = _body(request) or {}
    try:
        result = services.delete_job(payload.get("job_no", ""))
    except services.JobError as exc:
        return _error(exc)
    return JsonResponse({"message": f"Job card {result['job_no']} deleted."})


class JobCardListingView(LoginRequiredMixin, TemplateView):
    template_name = "job_card/job_card_listing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


def _listing_range(request):
    today = date.today()
    start = _parse(request.GET.get("start_date"), today)
    end = _parse(request.GET.get("end_date"), today)
    return start, end


@login_required
@require_GET
def job_listing_data(request):
    start, end = _listing_range(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse(services.job_card_listing(start, end))


@login_required
@require_GET
def job_listing_export(request):
    from django.http import HttpResponse

    from . import exports

    start, end = _listing_range(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    data = services.job_card_listing(start, end)
    body = exports.build_job_card_listing_workbook(data, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(body, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="Job_Card_List.xlsx"'
    return response


class JobCardSupervisorListingView(LoginRequiredMixin, TemplateView):
    template_name = "job_card/job_card_supervisor_listing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def job_supervisors(request):
    return JsonResponse({"supervisors": services.search_supervisors(request.GET.get("q", ""))})


def _supervisor_params(request):
    start, end = _listing_range(request)
    return start, end, (request.GET.get("supervisor") or "").strip()


@login_required
@require_GET
def job_supervisor_listing_data(request):
    start, end, code = _supervisor_params(request)
    if not code:
        return JsonResponse({"message": "Select a supervisor first."}, status=400)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse(services.job_card_supervisor_listing(start, end, code))


@login_required
@require_GET
def job_supervisor_listing_export(request):
    from django.http import HttpResponse

    from apps.supervisors.models import Supervisor

    from . import exports

    start, end, code = _supervisor_params(request)
    if not code or start > end:
        return JsonResponse({"message": "Select a supervisor and a valid date range."}, status=400)
    sup = Supervisor.objects.filter(code=code).values_list("name", flat=True).first() or code
    data = services.job_card_supervisor_listing(start, end, code)
    body = exports.build_job_card_supervisor_workbook(data, settings.BRAND["name"].upper(), start, end, sup)
    response = HttpResponse(body, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="Job_Card_Supervisor_List.xlsx"'
    return response


def _dmy(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


class JobCardPrintView(LoginRequiredMixin, TemplateView):
    template_name = "job_card/single_job_card.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job_no = (self.request.GET.get("job_no") or kwargs.get("job_no") or "").strip()
        context["job_no"] = job_no
        context["job"] = services.get_job(job_no) if job_no else None
        context["not_found"] = bool(job_no) and context["job"] is None
        if context["job"]:
            context["job_date_text"] = _dmy(context["job"]["job_date"])
            context["close_date_text"] = _dmy(context["job"]["close_date"]) if context["job"]["closed"] else ""
        context["company"] = settings.BRAND["name"].upper()
        context["address"] = settings.BRAND.get("address", "")
        return context


class JobCardShortListView(LoginRequiredMixin, TemplateView):
    template_name = "job_card/short_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_code"] = (self.request.GET.get("item") or "").strip().upper()
        context["qty"] = (self.request.GET.get("qty") or "").strip()
        context["with_rate"] = self.request.GET.get("rate") == "Y"
        context["data"] = None
        if context["item_code"] and context["qty"].isdigit():
            context["data"] = services.short_list(context["item_code"], Decimal(context["qty"]), context["with_rate"])
        context["not_found"] = bool(context["item_code"]) and context["qty"].isdigit() and context["data"] is None
        return context


@login_required
@require_GET
def job_short_list_export(request):
    from django.http import HttpResponse

    from . import exports

    item = (request.GET.get("item") or "").strip().upper()
    qty = (request.GET.get("qty") or "").strip()
    if not item or not qty.isdigit():
        return JsonResponse({"message": "Select an item and enter a quantity."}, status=400)
    data = services.short_list(item, Decimal(qty), request.GET.get("rate") == "Y")
    if data is None:
        return JsonResponse({"message": "Item not found."}, status=404)
    body = exports.build_short_list_workbook(data, settings.BRAND["name"].upper())
    response = HttpResponse(body, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="Short_List.xlsx"'
    return response


class ProductIssueView(LoginRequiredMixin, TemplateView):
    template_name = "job_card/product_issue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {"start_date": today.replace(day=1).isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def pi_list(request):
    start, end = _listing_range(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.product_issue_list(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def pi_open_jobs(request):
    item = (request.GET.get("item") or "").strip().upper()
    return JsonResponse({"jobs": services.product_issue_open_jobs(item) if item else []})


@login_required
@require_GET
def pi_preview(request):
    item = (request.GET.get("item") or "").strip().upper()
    job = (request.GET.get("job") or "").strip()
    try:
        return JsonResponse(services.product_issue_preview(item, job))
    except services.JobError as exc:
        return _error(exc)


@login_required
@require_GET
def pi_detail(request, serial):
    data = services.product_issue_detail(serial)
    if not data:
        return JsonResponse({"message": "Serial No. not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def pi_save(request):
    if not _can_edit(request.user):
        return _forbidden()
    payload = _body(request)
    if payload is None:
        return JsonResponse({"message": "Invalid request."}, status=400)
    mode = "modify" if payload.get("mode") == "modify" else "add"
    try:
        result = services.product_issue_save(payload, mode, username=request.user.get_username())
    except services.JobError as exc:
        return _error(exc)
    return JsonResponse({"message": f"Serial No. {result['serial_no']} saved.", "serial_no": result["serial_no"]})


@login_required
@require_POST
def pi_delete(request):
    if not _can_edit(request.user):
        return _forbidden()
    payload = _body(request) or {}
    try:
        result = services.product_issue_delete((payload.get("serial_no") or "").strip())
    except services.JobError as exc:
        return _error(exc)
    return JsonResponse({"message": f"Serial No. {result['serial_no']} deleted."})

import json
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."


def _can_edit(user):
    return services.writes_enabled() and user.has_perm(services.PERMISSION)


def _forbidden():
    if not services.writes_enabled():
        return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
    return JsonResponse({"message": "You don't have permission to change issue slips."}, status=403)


def _parse_date(raw, default=None):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


class IssueSlipEntryView(LoginRequiredMixin, TemplateView):
    template_name = "issue_slip/issue_slip_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {
            "rows": services.list_issue_slips(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


@login_required
@require_GET
def issue_slip_list(request):
    today = date.today()
    start = _parse_date(request.GET.get("start_date"), today)
    end = _parse_date(request.GET.get("end_date"), today)
    return JsonResponse({"rows": services.list_issue_slips(start, end)})


@login_required
@require_GET
def issue_slip_next_no(request):
    try:
        return JsonResponse({"mis_no": services.next_issue_no()})
    except services.IssueSlipError as exc:
        return JsonResponse({"message": str(exc)}, status=400)


@login_required
@require_GET
def issue_slip_detail(request, mis_no):
    order = services.get_issue_slip(mis_no)
    if not order:
        return JsonResponse({"message": "Issue slip not found."}, status=404)
    return JsonResponse(order)


@login_required
@require_POST
def reauthenticate(request):
    """Re-checks the CURRENT user's own account password (never a shared
    stored one) before Modify/Delete -- server-validated, per-user, and never
    exposing any stored password value to the browser. Same convention as
    apps.mrn.views.reauthenticate."""
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
def issue_slip_save(request):
    if not _can_edit(request.user):
        return _forbidden()
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    mis_date = None
    try:
        y, m, d = (payload.get("mis_date") or "").split("-")
        mis_date = date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        pass
    try:
        result = services.save_issue_slip(
            mis_date=mis_date,
            items=payload.get("items"),
            remarks=payload.get("remarks", ""),
            key=payload.get("key") or None,
            username=request.user.get_username()[:10],
        )
    except services.IssueSlipError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Issue Slip {result['mis_no']} saved.", "mis_no": result["mis_no"]})


@login_required
@require_POST
def issue_slip_delete(request):
    if not _can_edit(request.user):
        return _forbidden()
    mis_no = request.POST.get("mis_no", "")
    try:
        services.delete_issue_slip(mis_no)
    except services.IssueSlipError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Issue Slip {mis_no} deleted."})


# --- Single Issue Report ------------------------------------------------------------

class SingleIssueReportView(LoginRequiredMixin, TemplateView):
    template_name = "issue_slip/single_issue_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {
            "rows": services.single_issue_report(today, today),
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        }
        return context


def _single_issue_report_params(request):
    today = date.today()
    start = _parse_date(request.GET.get("start_date"), today)
    end = _parse_date(request.GET.get("end_date"), today)
    return start, end


@login_required
@require_GET
def single_issue_report_data(request):
    start, end = _single_issue_report_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.single_issue_report(start, end)
    return JsonResponse({"rows": rows, "start_date": start.isoformat(), "end_date": end.isoformat()})


@login_required
@require_GET
def single_issue_report_export(request):
    from . import exports

    start, end = _single_issue_report_params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    rows = services.single_issue_report(start, end)
    data = exports.build_single_issue_report_workbook(rows, settings.BRAND["name"].upper(), start, end)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    filename = f"Single_Issue_Report_{start.strftime('%d-%m-%Y')}_to_{end.strftime('%d-%m-%Y')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

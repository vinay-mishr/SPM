import json
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import sub_assembly as sa


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED and user.has_perm("job_card.change_jobcard")


def _parse_date(value, default):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


class SubAssemblyEntryView(LoginRequiredMixin, TemplateView):
    template_name = "job_card/sub_assembly_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit"] = _can_edit(self.request.user)
        today = date.today()
        context["initial_data"] = {"start_date": today.replace(day=1).isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def sa_list(request):
    today = date.today()
    start = _parse_date(request.GET.get("start_date"), today.replace(day=1))
    end = _parse_date(request.GET.get("end_date"), today)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": sa.list_entries(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def sa_next(request):
    return JsonResponse({"number": str(sa.next_no())})


@login_required
@require_GET
def sa_detail(request, number):
    try:
        data = sa.load(int(number))
    except ValueError:
        data = None
    if not data:
        return JsonResponse({"message": "Job no. not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def sa_save(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change job cards."}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    mode = body.get("mode")
    user = request.user.get_username()
    try:
        if mode == "add":
            result = sa.add(body, username=user)
        elif mode == "modify":
            result = sa.modify(int(body["number"]), body, username=user)
        elif mode == "close":
            result = sa.close(int(body["number"]), body, username=user)
        elif mode == "delete":
            result = sa.delete(int(body["number"]))
        else:
            return JsonResponse({"message": "Unknown action."}, status=400)
    except sa.SubAssemblyError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    except (KeyError, ValueError):
        return JsonResponse({"message": "Enter a valid job no."}, status=400)
    return JsonResponse({"message": f"Job card {result['job_no']} saved.", **result})

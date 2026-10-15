from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .forms import SupervisorForm
from .models import Supervisor

SAVING_OFF = {"message": "Saving to the SP_MACHINE database is switched off. Nothing was changed."}


class SupervisorMasterView(LoginRequiredMixin, TemplateView):
    template_name = "supervisors/supervisor_master_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"supervisors": services.list_supervisors()}
        return context


@login_required
@require_GET
def supervisor_list(request):
    return JsonResponse({"supervisors": services.list_supervisors()})


@login_required
@require_GET
def supervisor_next_code(request):
    try:
        return JsonResponse({"code": services.next_code(request.GET.get("name", ""))})
    except services.SupervisorError as exc:
        return JsonResponse({"code": "", "message": str(exc)})


@login_required
@require_POST
def supervisor_save(request, code=None):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    supervisor = get_object_or_404(Supervisor, pk=code) if code else None
    form = SupervisorForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    try:
        saved = services.update(supervisor, form.cleaned_data) if supervisor else services.create(
            form.cleaned_data, request.user.get_username()
        )
    except services.SupervisorError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    action = "updated" if supervisor else "added"
    return JsonResponse({"supervisor": services.serialize(saved), "message": f"Supervisor {saved.code} {action}."})


@login_required
@require_POST
def supervisor_delete(request, code):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    supervisor = get_object_or_404(Supervisor, pk=code)
    try:
        services.delete(supervisor)
    except services.SupervisorError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Supervisor {code} deleted."})

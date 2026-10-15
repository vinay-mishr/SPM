from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .forms import MarketingManagerForm
from .models import MarketingManager

SAVING_OFF = {"message": "Saving to the SP_MACHINE database is switched off. Nothing was changed."}


class MarketingManagerView(LoginRequiredMixin, TemplateView):
    template_name = "marketing/marketing_manager_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"managers": services.list_managers()}
        return context


@login_required
@require_GET
def manager_list(request):
    return JsonResponse({"managers": services.list_managers()})


@login_required
@require_GET
def manager_next_code(request):
    try:
        return JsonResponse({"code": services.next_code()})
    except services.ManagerError as exc:
        return JsonResponse({"code": "", "message": str(exc)})


@login_required
@require_POST
def manager_save(request, code=None):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    manager = get_object_or_404(MarketingManager, pk=code) if code else None
    form = MarketingManagerForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    try:
        if manager:
            saved = services.update(manager, form.cleaned_data)
        else:
            saved = services.create(form.cleaned_data, request.user.get_username())
    except services.ManagerError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    action = "updated" if manager else "added"
    return JsonResponse({"manager": services.serialize(saved), "message": f"Manager {saved.code} {action}."})


@login_required
@require_POST
def manager_delete(request, code):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    manager = get_object_or_404(MarketingManager, pk=code)
    try:
        services.delete(manager)
    except services.ManagerError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Manager {code} deleted."})

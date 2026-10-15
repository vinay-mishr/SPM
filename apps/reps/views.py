from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .forms import RepForm
from .models import Rep

SAVING_OFF = {"message": "Saving to the SP_MACHINE database is switched off. Nothing was changed."}


class RepMasterView(LoginRequiredMixin, TemplateView):
    template_name = "reps/rep_master_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"reps": services.list_reps()}
        return context


@login_required
@require_GET
def rep_list(request):
    return JsonResponse({"reps": services.list_reps()})


@login_required
@require_GET
def rep_next_code(request):
    try:
        return JsonResponse({"code": services.next_code()})
    except services.RepError as exc:
        return JsonResponse({"code": "", "message": str(exc)})


@login_required
@require_POST
def rep_save(request, code=None):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    rep = get_object_or_404(Rep, pk=code) if code else None
    form = RepForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    try:
        saved = services.update(rep, form.cleaned_data) if rep else services.create(
            form.cleaned_data, request.user.get_username()
        )
    except services.RepError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    action = "updated" if rep else "added"
    return JsonResponse({"rep": services.serialize(saved), "message": f"Rep {saved.code} {action}."})


@login_required
@require_POST
def rep_delete(request, code):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    rep = get_object_or_404(Rep, pk=code)
    try:
        services.delete(rep)
    except services.RepError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Rep {code} deleted."})

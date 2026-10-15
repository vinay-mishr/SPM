from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .forms import MaterialForm
from .models import Material

SAVING_OFF = {"message": "Saving to the SP_MACHINE database is switched off. Nothing was changed."}


class MaterialMasterView(LoginRequiredMixin, TemplateView):
    template_name = "materials/material_master_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"materials": services.list_materials()}
        return context


@login_required
@require_GET
def material_list(request):
    return JsonResponse({"materials": services.list_materials()})


@login_required
@require_GET
def material_next_code(request):
    try:
        return JsonResponse({"code": services.next_code(request.GET.get("name", ""))})
    except services.MaterialError as exc:
        return JsonResponse({"code": "", "message": str(exc)})


@login_required
@require_POST
def material_save(request, code=None):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    material = get_object_or_404(Material, pk=code) if code else None
    form = MaterialForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    try:
        saved = services.update(material, form.cleaned_data) if material else services.create(
            form.cleaned_data, request.user.get_username()
        )
    except services.MaterialError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    action = "updated" if material else "added"
    return JsonResponse({"material": services.serialize(saved), "message": f"Material {saved.code} {action}."})


@login_required
@require_POST
def material_delete(request, code):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    material = get_object_or_404(Material, pk=code)
    try:
        services.delete(material)
    except services.MaterialError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Material {code} deleted."})

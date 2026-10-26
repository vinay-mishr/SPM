from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import exports, services
from .forms import PartForm
from .models import Part

SAVING_OFF = {"message": "Saving to the SP_MACHINE database is switched off. Nothing was changed."}
DUPLICATE_MESSAGE = "This part number exists more than once in the old data; it cannot be {} here."


def _get_part(code):
    """
    A handful of old part numbers repeat in part-mst (no real key), so a plain
    get_object_or_404 would crash with MultipleObjectsReturned. Fetch the first
    matching row instead; services.duplicate_part_numbers() blocks writes on those.
    """
    part = Part.objects.filter(pk=code).first()
    if part is None:
        raise Http404
    return part


class PartMasterView(LoginRequiredMixin, TemplateView):
    template_name = "parts/part_master_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        parts = services.list_parts()
        context["initial_data"] = {"parts": parts}
        context["material_suggestions"] = services.material_names()
        return context


@login_required
@require_GET
def part_list(request):
    return JsonResponse({"parts": services.list_parts()})


@login_required
@require_GET
def party_search(request):
    return JsonResponse({"parties": services.search_parties(request.GET.get("q", ""))})


@login_required
@require_POST
def part_save(request, code=None):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    part = _get_part(code) if code else None
    if part and part.part_number in services.duplicate_part_numbers():
        return JsonResponse({"message": DUPLICATE_MESSAGE.format("modified")}, status=409)
    form = PartForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    try:
        saved = services.update(part, form.cleaned_data) if part else services.create(
            form.cleaned_data, request.user.get_username()
        )
    except services.PartError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    action = "updated" if part else "added"
    return JsonResponse({"part": services.serialize(saved), "message": f"Part {saved.part_number} {action}."})


@login_required
@require_POST
def part_delete(request, code):
    if not services.writes_enabled():
        return JsonResponse(SAVING_OFF, status=403)
    part = _get_part(code)
    if part.part_number in services.duplicate_part_numbers():
        return JsonResponse({"message": DUPLICATE_MESSAGE.format("deleted")}, status=409)
    try:
        services.delete(part)
    except services.PartError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Part {code} deleted."})


@login_required
@require_GET
def part_export(request):
    data = exports.build_workbook()
    response = HttpResponse(
        data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="part_master.xlsx"'
    return response

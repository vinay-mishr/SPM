import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import exports, services

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."


def _can_edit(user):
    return services.writes_enabled() and user.has_perm(services.PERMISSION)


class BomMasterView(LoginRequiredMixin, TemplateView):
    template_name = "bom/bom_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        context.update(
            can_edit=can_edit,
            initial_data={"parents": services.list_parents(), "can_edit": can_edit},
        )
        return context


@login_required
@require_GET
def bom_list(request):
    return JsonResponse({"parents": services.list_parents()})


@login_required
@require_GET
def bom_detail(request, part_code):
    return JsonResponse({"part_code": part_code, "components": services.get_components(part_code)})


@login_required
@require_GET
def part_search(request):
    return JsonResponse({"parts": services.search_parts(request.GET.get("q", ""))})


@login_required
@require_GET
def item_search(request):
    return JsonResponse({"items": services.search_items(request.GET.get("q", ""))})


@login_required
@require_POST
def bom_save(request):
    if not _can_edit(request.user):
        if not services.writes_enabled():
            return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
        return JsonResponse({"message": "You don't have permission to change the Bill of Material."}, status=403)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        count = services.save(payload.get("part_code"), payload.get("components"), request.user.get_username())
    except services.BomError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({
        "message": f"Bill of Material saved for {payload.get('part_code')} ({count} component{'s' if count != 1 else ''}).",
        "parents": services.list_parents(),
    })


@login_required
@require_POST
def bom_delete(request, part_code):
    if not _can_edit(request.user):
        if not services.writes_enabled():
            return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
        return JsonResponse({"message": "You don't have permission to change the Bill of Material."}, status=403)
    try:
        services.delete_bom(part_code)
    except services.BomError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Bill of Material deleted for {part_code}."})


# --- Bill of Material Master (plain, Item-wise) --------------------------------------------

class BomItemMasterView(LoginRequiredMixin, TemplateView):
    template_name = "bom/bom_item_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        context.update(
            can_edit=can_edit,
            initial_data={"parents": services.list_item_parents(), "can_edit": can_edit},
        )
        return context


@login_required
@require_GET
def bom_item_list(request):
    return JsonResponse({"parents": services.list_item_parents()})


@login_required
@require_GET
def bom_item_detail(request, item_code):
    return JsonResponse({"item_code": item_code, "components": services.get_components_for_item(item_code)})


@login_required
@require_POST
def bom_item_save(request):
    if not _can_edit(request.user):
        if not services.writes_enabled():
            return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
        return JsonResponse({"message": "You don't have permission to change the Bill of Material."}, status=403)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        count = services.save_for_item(payload.get("item_code"), payload.get("components"), request.user.get_username())
    except services.BomError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({
        "message": f"Bill of Material saved for {payload.get('item_code')} ({count} component{'s' if count != 1 else ''}).",
        "parents": services.list_item_parents(),
    })


@login_required
@require_POST
def bom_item_delete(request, item_code):
    if not _can_edit(request.user):
        if not services.writes_enabled():
            return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
        return JsonResponse({"message": "You don't have permission to change the Bill of Material."}, status=403)
    try:
        services.delete_bom_for_item(item_code)
    except services.BomError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Bill of Material deleted for {item_code}."})


# --- Consumption Master report --------------------------------------------------------------

class ConsumptionMasterView(LoginRequiredMixin, TemplateView):
    template_name = "bom/consumption_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"data": None}
        return context


@login_required
@require_GET
def consumption_master_data(request):
    item_code = request.GET.get("item_code", "").strip()
    data = services.consumption_master(item_code)
    if data is None:
        return JsonResponse({"message": "That item was not found in Item Master."}, status=404)
    return JsonResponse({"data": data})


@login_required
@require_GET
def consumption_master_export(request):
    item_code = request.GET.get("item_code", "").strip()
    data = services.consumption_master(item_code)
    if data is None:
        return JsonResponse({"message": "That item was not found in Item Master."}, status=404)
    workbook = exports.build_consumption_master_workbook(data, settings.BRAND["name"].upper())
    response = HttpResponse(workbook, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="consumption_master_{data["item_code"]}.xlsx"'
    return response


# --- Bill of Material Master Without Value report --------------------------------------------

class BomWithoutValueView(LoginRequiredMixin, TemplateView):
    template_name = "bom/bom_without_value.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"data": None}
        return context


@login_required
@require_GET
def bom_without_value_data(request):
    item_code = request.GET.get("item_code", "").strip()
    data = services.bom_without_value(item_code)
    if data is None:
        return JsonResponse({"message": "That item was not found in Item Master."}, status=404)
    return JsonResponse({"data": data})


@login_required
@require_GET
def bom_without_value_export(request):
    item_code = request.GET.get("item_code", "").strip()
    data = services.bom_without_value(item_code)
    if data is None:
        return JsonResponse({"message": "That item was not found in Item Master."}, status=404)
    workbook = exports.build_bom_without_value_workbook(data, settings.BRAND["name"].upper())
    response = HttpResponse(workbook, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="bom_without_value_{data["item_code"]}.xlsx"'
    return response


# --- Bill of Material Master Value-Wise report (Sub Assembly, Part Master parent) ------------

class SaValueWiseView(LoginRequiredMixin, TemplateView):
    template_name = "bom/sa_value_wise.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"data": None}
        return context


@login_required
@require_GET
def sa_value_wise_data(request):
    part_code = request.GET.get("part_code", "").strip()
    data = services.sa_value_wise(part_code)
    if data is None:
        return JsonResponse({"message": "That part was not found in Part Master."}, status=404)
    return JsonResponse({"data": data})


@login_required
@require_GET
def sa_value_wise_export(request):
    part_code = request.GET.get("part_code", "").strip()
    data = services.sa_value_wise(part_code)
    if data is None:
        return JsonResponse({"message": "That part was not found in Part Master."}, status=404)
    workbook = exports.build_sa_value_wise_workbook(data, settings.BRAND["name"].upper())
    response = HttpResponse(workbook, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="bom_value_wise_{data["item_code"]}.xlsx"'
    return response


# --- Bill of Material Master Suppliers report (Sub Assembly, no value) -----------------------

class SaSuppliersView(LoginRequiredMixin, TemplateView):
    template_name = "bom/sa_suppliers.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"data": None}
        return context


@login_required
@require_GET
def sa_suppliers_data(request):
    part_code = request.GET.get("part_code", "").strip()
    data = services.sa_without_value_suppliers(part_code)
    if data is None:
        return JsonResponse({"message": "That part was not found in Part Master."}, status=404)
    return JsonResponse({"data": data})


@login_required
@require_GET
def sa_suppliers_export(request):
    part_code = request.GET.get("part_code", "").strip()
    data = services.sa_without_value_suppliers(part_code)
    if data is None:
        return JsonResponse({"message": "That part was not found in Part Master."}, status=404)
    workbook = exports.build_sa_suppliers_workbook(data, settings.BRAND["name"].upper())
    response = HttpResponse(workbook, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="bom_suppliers_{data["item_code"]}.xlsx"'
    return response

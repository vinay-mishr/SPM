from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .forms import ItemForm
from .models import Item

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off until it is approved. Nothing was changed."


def _saving_off():
    return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)


# Matches the old software's unit table (dbo.unit).
UNIT_SUGGESTIONS = ["NUM", "UNT", "SET", "PCS", "KG", "MTR", "LIT", "PKT", "BOX", "DAY", "MIL"]


class ItemMasterView(LoginRequiredMixin, TemplateView):
    template_name = "items/item_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {
            "items": services.list_items(),
            "next_code": services.next_item_code(),
            "read_only": not services.writes_enabled(),
        }
        context["read_only"] = not services.writes_enabled()
        context["unit_suggestions"] = UNIT_SUGGESTIONS
        return context


@login_required
@require_GET
def item_list(request):
    return JsonResponse({"items": services.list_items(), "next_code": services.next_item_code()})


@login_required
@require_POST
def item_save(request, pk=None):
    if not services.writes_enabled():
        return _saving_off()
    item = get_object_or_404(Item, pk=pk) if pk else None
    form = ItemForm(request.POST, instance=item)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    try:
        saved = services.update_item(form) if item else services.create_item(form, request.user.get_username())
    except services.ItemCodeConflictError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    action = "updated" if item else "added"
    return JsonResponse(
        {"item": services.serialize_item(saved), "message": f"Item {saved.item_code} {action}."}
    )


@login_required
@require_POST
def item_delete(request, pk):
    if not services.writes_enabled():
        return _saving_off()
    item = get_object_or_404(Item, pk=pk)
    code = item.item_code
    try:
        services.delete_item(item)
    except services.ItemInUseError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Item {code} deleted."})

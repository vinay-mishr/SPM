from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .models import Unit

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."


def _can_edit(user):
    return services.writes_enabled() and user.has_perm(services.PERMISSION)


def _forbidden(user):
    if not services.writes_enabled():
        return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
    return JsonResponse({"message": "You don't have permission to change the Unit Master."}, status=403)


class UnitMasterView(LoginRequiredMixin, TemplateView):
    template_name = "units/unit_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        context.update(
            can_edit=can_edit,
            initial_data={"units": services.list_units(), "can_edit": can_edit},
        )
        return context


@login_required
@require_GET
def unit_list(request):
    return JsonResponse({"units": services.list_units()})


@login_required
@require_POST
def unit_save(request, pk=None):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    unit = Unit.objects.filter(pk=pk).first() if pk else None
    if pk and unit is None:
        raise Http404
    try:
        if unit:
            saved = services.update(unit, request.POST.get("name"))
        else:
            saved = services.create(request.POST.get("name"), request.user.get_username())
    except services.UnitError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    action = "updated" if unit else "added"
    return JsonResponse({"unit": services.serialize(saved), "message": f"Unit {saved.name} {action}."})


@login_required
@require_POST
def unit_delete(request, pk):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    unit = Unit.objects.filter(pk=pk).first()
    if unit is None:
        raise Http404
    name = unit.name
    try:
        services.delete(unit)
    except services.UnitError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Unit {name} deleted."})

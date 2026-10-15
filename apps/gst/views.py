import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .models import GstRate

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."


def _can_edit(user):
    return services.writes_enabled() and user.has_perm(services.PERMISSION)


def _forbidden(user):
    if not services.writes_enabled():
        return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
    return JsonResponse({"message": "You don't have permission to change the GST Master."}, status=403)


class GstMasterView(LoginRequiredMixin, TemplateView):
    template_name = "gst/gst_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        context.update(
            can_edit=can_edit,
            initial_data={"rates": services.list_rates(), "can_edit": can_edit},
        )
        return context


@login_required
@require_GET
def gst_list(request):
    return JsonResponse({"rates": services.list_rates()})


@login_required
@require_GET
def gst_check(request):
    """ADD/MODIFY's key-field check: does this GST % already exist?"""
    raw_rate = request.GET.get("rate", "")
    try:
        rate = services.parse_rate(raw_rate)
    except services.GstError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    obj = GstRate.objects.filter(rate=rate).first()
    return JsonResponse({"exists": obj is not None, "data": services.serialize(obj) if obj else None})


@login_required
@require_POST
def gst_save(request):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)

    mode = payload.get("mode")
    raw_rate = payload.get("rate")
    try:
        if mode == "add":
            obj = services.create(raw_rate, payload, request.user.get_username())
        elif mode == "modify":
            obj = services.update(raw_rate, payload)
        else:
            return JsonResponse({"message": "Invalid request."}, status=400)
    except services.GstError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)

    return JsonResponse({"rate": services.serialize(obj), "message": f"GST rate {obj.rate}% saved."})


@login_required
@require_POST
def gst_delete(request, rate):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    try:
        services.delete(rate)
    except services.GstError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"GST rate {rate}% deleted."})

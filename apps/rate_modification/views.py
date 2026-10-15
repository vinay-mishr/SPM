import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services


class RateModificationView(LoginRequiredMixin, TemplateView):
    template_name = "rate_modification/rate_modification.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = services.writes_enabled() and self.request.user.has_perm(services.PERMISSION)
        context["can_edit"] = can_edit
        context["initial_data"] = {"rows": services.rows(), "can_edit": can_edit}
        return context


@login_required
@require_GET
def rate_data(request):
    return JsonResponse({"rows": services.rows()})


@login_required
@require_POST
def rate_save(request):
    if not services.writes_enabled():
        return JsonResponse(
            {"message": "Saving to the SP_MACHINE database is switched off. Nothing was changed."}, status=403
        )
    if not request.user.has_perm(services.PERMISSION):
        return JsonResponse({"message": "You don't have permission to modify rates."}, status=403)
    try:
        changes = json.loads(request.body or b"{}").get("changes")
    except (ValueError, AttributeError):
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        count = services.save(changes, request.user.get_username())
    except services.RateModificationError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({
        "message": f"Rate updated for {count} part{'s' if count != 1 else ''}.",
        "rows": services.rows(),
    })

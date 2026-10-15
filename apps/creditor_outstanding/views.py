from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .forms import CreditorOutstandingForm


def _can_edit(user):
    return services.writes_enabled() and user.has_perm(services.PERMISSION)


def _forbidden(user):
    if not services.writes_enabled():
        return JsonResponse({"message": "Saving to the SP_MACHINE database is switched off. Nothing was changed."}, status=403)
    return JsonResponse({"message": "You don't have permission to change creditor outstanding."}, status=403)


def _key(request):
    """The selected bill: DIV | bill no | party code (the table has no key of its own)."""
    parts = (request.POST.get("key") or "").split("|")
    return tuple(parts) if len(parts) == 3 else None


class CreditorOutstandingView(LoginRequiredMixin, TemplateView):
    template_name = "creditor_outstanding/creditor_outstanding_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        context.update(
            can_edit=can_edit,
            divisions=services.divisions(),
            default_div=services.DEFAULT_DIV,
            initial_data={
                "bills": services.list_bills(services.DEFAULT_DIV),
                "default_div": services.DEFAULT_DIV,
                "can_edit": can_edit,
            },
        )
        return context


@login_required
@require_GET
def bill_list(request):
    return JsonResponse({"bills": services.list_bills(request.GET.get("div", services.DEFAULT_DIV))})


@login_required
@require_GET
def vendor_search(request):
    return JsonResponse({"parties": services.search_parties(request.GET.get("q", ""))})


@login_required
@require_POST
def bill_save(request):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    form = CreditorOutstandingForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    key = _key(request)
    try:
        if key:
            services.update(key, form.cleaned_data)
        else:
            services.create(form.cleaned_data, request.user.get_username())
    except services.OutstandingError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    data = form.cleaned_data
    return JsonResponse({
        "message": f"Invoice {data['div']}/{data['bill_no']} {'updated' if key else 'added'}.",
        "key": f"{data['div']}|{data['bill_no']}|{data['party_code']}",
    })


@login_required
@require_POST
def bill_delete(request):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    key = _key(request)
    if not key:
        return JsonResponse({"message": "Select an entry first."}, status=400)
    try:
        services.delete(key)
    except services.OutstandingError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Invoice {key[0]}/{key[1]} deleted."})

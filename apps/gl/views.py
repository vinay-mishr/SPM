import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import opening_balance, services
from .models import Ledger

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."


def _can_edit(user):
    return services.writes_enabled() and user.has_perm(services.PERMISSION)


def _forbidden(user):
    if not services.writes_enabled():
        return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
    return JsonResponse({"message": "You don't have permission to change the General Ledger."}, status=403)


class LedgerMasterView(LoginRequiredMixin, TemplateView):
    template_name = "gl/ledger_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = _can_edit(self.request.user)
        context.update(
            can_edit=can_edit,
            initial_data={"ledgers": services.list_ledgers(), "groups": services.groups(), "tree_groups": services.tree_groups(), "can_edit": can_edit},
        )
        return context


@login_required
@require_GET
def ledger_list(request):
    return JsonResponse({"ledgers": services.list_ledgers()})


@login_required
@require_GET
def ledger_next_code(request):
    try:
        return JsonResponse({"code": services.next_ledger_code(request.GET.get("description", ""))})
    except services.LedgerError as exc:
        return JsonResponse({"code": "", "message": str(exc)})


@login_required
@require_POST
def ledger_save(request, pk=None):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    ledger = Ledger.objects.filter(pk=pk).first() if pk else None
    if pk and ledger is None:
        raise Http404
    try:
        if ledger:
            saved = services.update(ledger, request.POST)
        else:
            saved = services.create(request.POST, request.user.get_username())
    except services.LedgerError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    action = "updated" if ledger else "added"
    return JsonResponse({"ledger": services.serialize(saved), "message": f"Ledger {saved.ledger_code} {action}."})


@login_required
@require_POST
def ledger_delete(request, pk):
    if not _can_edit(request.user):
        return _forbidden(request.user)
    ledger = Ledger.objects.filter(pk=pk).first()
    if ledger is None:
        raise Http404
    code = ledger.ledger_code
    try:
        services.delete(ledger)
    except services.LedgerError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Ledger {code} deleted."})


# --- Main Ledger (Op. Balance) ------------------------------------------------------------


class LedgerOpeningBalanceView(LoginRequiredMixin, TemplateView):
    template_name = "gl/main_ledger_opening_balance.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = services.writes_enabled() and self.request.user.has_perm(opening_balance.PERMISSION)
        context["can_edit"] = can_edit
        context["initial_data"] = {
            "rows": opening_balance.rows(),
            "totals": opening_balance.totals(),
            "can_edit": can_edit,
        }
        return context


@login_required
@require_GET
def opening_balance_data(request):
    return JsonResponse({"rows": opening_balance.rows(), "totals": opening_balance.totals()})


@login_required
@require_POST
def opening_balance_save(request):
    if not services.writes_enabled():
        return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)
    if not request.user.has_perm(opening_balance.PERMISSION):
        return JsonResponse({"message": "You don't have permission to change ledger opening balances."}, status=403)
    try:
        changes = json.loads(request.body or b"{}").get("changes")
    except (ValueError, AttributeError):
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        count = opening_balance.save(changes)
    except opening_balance.OpeningBalanceError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({
        "message": f"Opening balances saved for {count} ledger{'s' if count != 1 else ''}.",
        "rows": opening_balance.rows(),
        "totals": opening_balance.totals(),
    })

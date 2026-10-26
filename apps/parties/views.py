import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import exports, opening_balance, services
from .choices import GstCategory, SupplyType
from .forms import PartyForm
from .models import Party

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."


def _saving_off():
    return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)


class PartyMasterView(LoginRequiredMixin, TemplateView):
    template_name = "parties/party_master_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        read_only = not services.writes_enabled()
        context.update(
            initial_data={
                "parties": services.list_parties(),
                "company_state_code": services.company_state_code(),
                "read_only": read_only,
            },
            read_only=read_only,
            states=services.states(),
            mkt_managers=services.mkt_managers(),
            reps=services.reps(),
            gst_categories=GstCategory.choices,
            supply_types=SupplyType.choices,
            suggestions=services.suggestions(),
        )
        return context


@login_required
@require_GET
def party_list(request):
    return JsonResponse({"parties": services.list_parties(), "suggestions": services.suggestions()})


@login_required
@require_GET
def party_next_code(request):
    """Preview of the code a new party would get (depends on the first letter of the name)."""
    try:
        return JsonResponse({"code": services.next_party_code(request.GET.get("name", ""))})
    except services.PartyCodeError as exc:
        return JsonResponse({"code": "", "message": str(exc)})


@login_required
@require_GET
def party_gstin_lookup(request):
    """Auto-fill support for the Add/Modify form: looks up a GSTIN against the
    configured GST provider and returns whatever fields it actually has.
    Never fabricates a result -- an invalid GSTIN or a provider miss/failure
    is reported as an error, and the form falls back to manual entry."""
    gstin = (request.GET.get("gstin") or "").strip()
    try:
        return JsonResponse({"fields": services.lookup_gstin_details(gstin)})
    except services.GstinLookupError as exc:
        return JsonResponse({"message": str(exc)}, status=400)


@login_required
@require_POST
def party_save(request, pk=None):
    if not services.writes_enabled():
        return _saving_off()
    party = get_object_or_404(Party, pk=pk) if pk else None
    original = services.serialize_party(party) if party else None
    form = PartyForm(request.POST, original=original)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    try:
        if party:
            saved = services.update_party(party, form)
        else:
            saved = services.create_party(form, request.user.get_username())
    except services.PartyCodeError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    action = "updated" if party else "added"
    return JsonResponse(
        {"party": services.serialize_party(saved), "message": f"Party {saved.party_code} {action}."}
    )


@login_required
@require_POST
def party_delete(request, pk):
    if not services.writes_enabled():
        return _saving_off()
    party = get_object_or_404(Party, pk=pk)
    code = party.party_code
    try:
        services.delete_party(party)
    except services.PartyInUseError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Party {code} deleted."})


@login_required
@require_GET
def party_export(request, kind):
    """DEBTORS / CREDITORS printing: Excel list read from the old software's cust_mst."""
    if kind not in exports.LAYOUTS:
        raise Http404
    try:
        parties = exports.fetch_parties(kind)
    except exports.LegacyDatabaseMissing as exc:
        return HttpResponse(str(exc), status=503, content_type="text/plain")
    data = exports.build_workbook(kind, parties, settings.BRAND["name"].upper())
    response = HttpResponse(
        data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{kind}_list.xlsx"'
    return response


# --- Opening Balance Master ---------------------------------------------------------------


class OpeningBalanceView(LoginRequiredMixin, TemplateView):
    template_name = "parties/opening_balance.html"

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
        return _saving_off()
    if not request.user.has_perm(opening_balance.PERMISSION):
        return JsonResponse({"message": "You don't have permission to change opening balances."}, status=403)
    try:
        changes = json.loads(request.body or b"{}").get("changes")
    except (ValueError, AttributeError):
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        count = opening_balance.save(changes)
    except opening_balance.OpeningBalanceError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({
        "message": f"Opening balances saved for {count} part{'y' if count == 1 else 'ies'}.",
        "rows": opening_balance.rows(),
        "totals": opening_balance.totals(),
    })

import json
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from apps.parties.models import Party

from . import services
from .models import DebitNote


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED and user.has_perm("debit_note.change_debitnote")


def _range(request):
    today = date.today()
    start = _parse(request.GET.get("start_date"), today)
    end = _parse(request.GET.get("end_date"), today)
    return start, end


def _parse(value, default):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


class DebitNoteView(LoginRequiredMixin, TemplateView):
    template_name = "debit_note/debit_note.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def dn_list(request):
    start, end = _range(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.list_notes(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def dn_next_no(request):
    return JsonResponse({"dn_no": services.next_no()})


@login_required
@require_GET
def dn_detail(request, dn_no):
    data = services.detail(dn_no)
    if not data:
        return JsonResponse({"message": "Debit note not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_GET
def dn_parties(request):
    term = (request.GET.get("q") or "").strip()
    qs = Party.objects.all()
    if term:
        qs = qs.filter(name__icontains=term) | qs.filter(party_code__istartswith=term)
    return JsonResponse({"parties": [{"code": c, "name": (n or "").strip(), "city": (ct or "").strip()}
                                     for c, n, ct in qs.order_by("name").values_list("party_code", "name", "city")[:200]]})


@login_required
@require_POST
def dn_save(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change debit notes."}, status=403)
    body = _body(request)
    if body is None:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        if body.get("key"):
            result = services.save(body, key=body["key"], username=request.user.get_username())
        else:
            result = services.new_note_save(body, username=request.user.get_username())
    except services.DebitNoteError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Debit note {result['dn_no']} saved.", "dn_no": result["dn_no"]})


@login_required
@require_POST
def dn_delete(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change debit notes."}, status=403)
    body = _body(request) or {}
    try:
        services.delete((body.get("dn_no") or "").strip())
    except services.DebitNoteError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Debit note {body.get('dn_no')} deleted."})

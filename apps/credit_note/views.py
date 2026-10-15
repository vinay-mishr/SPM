"""GST Credit Note Entry views."""
import json
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from apps.bom.services import search_parts
from apps.parties.models import Party
from apps.parts.models import Part

from . import services

CREDIT_NOTE_PERMISSION = "credit_note.change_creditnote"


def _parse(raw, default):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED and user.has_perm(CREDIT_NOTE_PERMISSION)


def _forbidden():
    return JsonResponse({"message": "You don't have permission to change credit notes."}, status=403)


class CreditNoteEntryView(LoginRequiredMixin, TemplateView):
    template_name = "credit_note/credit_note_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def cn_list(request):
    today = date.today()
    start = _parse(request.GET.get("start_date"), today)
    end = _parse(request.GET.get("end_date"), today)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.list_notes(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def cn_next_no(request):
    return JsonResponse({"cn_no": services.next_cn_no()})


@login_required
@require_GET
def cn_detail(request, cn_no):
    data = services.detail(cn_no)
    if not data:
        return JsonResponse({"message": "Credit note not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_GET
def cn_parties(request):
    term = (request.GET.get("q") or "").strip()
    qs = Party.objects.all()
    if term:
        qs = qs.filter(name__icontains=term) | qs.filter(party_code__istartswith=term)
    return JsonResponse({"parties": [{"code": c, "name": (n or "").strip(), "city": (ct or "").strip()}
                                     for c, n, ct in qs.order_by("name").values_list("party_code", "name", "city")[:200]]})


@login_required
@require_GET
def cn_items(request):
    return JsonResponse({"items": [{"code": p["code"], "name": p["name"], "unit": p["unit"]}
                                   for p in search_parts(request.GET.get("q", ""))]})


@login_required
@require_GET
def cn_part(request):
    part = Part.objects.filter(part_number=(request.GET.get("code") or "").strip().upper()).first()
    if not part:
        return JsonResponse({"message": "Item not found."}, status=404)
    return JsonResponse({"code": part.part_number, "name": (part.description_1 or "").strip(),
                         "hsn": (part.hsn_code or "").strip(), "unit": (part.unit or "").strip(),
                         "rate": f"{(part.sale_rate or 0):.2f}", "gst_pct": f"{(part.gst_percent or 0):.2f}"})


@login_required
@require_POST
def cn_save(request):
    if not _can_edit(request.user):
        return _forbidden()
    body = _body(request)
    if body is None:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        if body.get("key"):
            result = services.save(body, key=body["key"], username=request.user.get_username())
        else:
            result = services.new_save(body, username=request.user.get_username())
    except services.CreditNoteError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Credit note {result['cn_no']} saved.", "cn_no": result["cn_no"]})


@login_required
@require_POST
def cn_delete(request):
    if not _can_edit(request.user):
        return _forbidden()
    body = _body(request) or {}
    try:
        services.delete((body.get("cn_no") or "").strip())
    except services.CreditNoteError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Credit note {body.get('cn_no')} deleted."})


class CreditNotePrintView(LoginRequiredMixin, TemplateView):
    template_name = "credit_note/credit_note_print.html"

    def get_context_data(self, **kwargs):
        from apps.creditor_outstanding.remittance import amount_in_words

        context = super().get_context_data(**kwargs)
        data = services.detail(kwargs["cn_no"])
        if not data:
            raise Http404("Credit note not found.")
        context["note"] = data
        context["brand_name"] = settings.BRAND["name"].upper()
        context["in_words"] = amount_in_words(data["net"])
        context["preview"] = self.request.GET.get("preview") == "1"
        return context

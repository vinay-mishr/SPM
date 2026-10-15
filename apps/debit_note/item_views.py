import json
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from apps.bom.services import search_parts
from apps.parts.models import Part

from . import item_services
from .services import DebitNoteError, next_no


def _parse(value, default):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED and user.has_perm("debit_note.change_debitnote")


class DebitNoteEntryView(LoginRequiredMixin, TemplateView):
    template_name = "debit_note/debit_note_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def ie_list(request):
    today = date.today()
    start = _parse(request.GET.get("start_date"), today)
    end = _parse(request.GET.get("end_date"), today)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": item_services.list_items(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def ie_next_no(request):
    return JsonResponse({"dn_no": next_no()})


@login_required
@require_GET
def ie_detail(request, dn_no):
    data = item_services.detail_items(dn_no)
    if not data:
        return JsonResponse({"message": "Debit note not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_GET
def ie_items(request):
    return JsonResponse({"items": [{"code": p["code"], "name": p["name"], "unit": p["unit"], "material": p["material"],
                                    "gst": p.get("gst_percent") or ""}
                                   for p in search_parts(request.GET.get("q", ""))]})


@login_required
@require_GET
def ie_part(request):
    part = Part.objects.filter(part_number=(request.GET.get("code") or "").strip().upper()).first()
    if not part:
        return JsonResponse({"message": "Item not found."}, status=404)
    return JsonResponse({"code": part.part_number, "name": (part.description_1 or "").strip(),
                         "hsn": (part.hsn_code or "").strip(), "unit": (part.unit or "").strip(),
                         "rate": f"{(part.purchase_rate or 0):.2f}", "mrp": f"{(part.sale_rate or 0):.2f}",
                         "gst_pct": f"{(part.gst_percent or 0):.2f}"})


@login_required
@require_POST
def ie_save(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change debit notes."}, status=403)
    body = _body(request)
    if body is None:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        if body.get("key"):
            result = item_services.save_items(body, key=body["key"], username=request.user.get_username())
        else:
            result = item_services.new_save_items(body, username=request.user.get_username())
    except DebitNoteError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Debit note {result['dn_no']} saved.", "dn_no": result["dn_no"]})


@login_required
@require_POST
def ie_delete(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change debit notes."}, status=403)
    body = _body(request) or {}
    try:
        item_services.delete_items((body.get("dn_no") or "").strip())
    except DebitNoteError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Debit note {body.get('dn_no')} deleted."})

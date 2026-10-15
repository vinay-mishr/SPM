"""Quotation (Spare Part) views -- listing, entry (add / modify / view), save / confirm / delete, print."""
import json
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.quotations.services import QuotationError as _TokenError  # run_once (reused) raises this for a bad/expired token

from . import services
from .services import QuotationSparepartError


def _can_edit(user):
    return services.writes_enabled()


def _json_error(message, status=400, errors=None):
    return JsonResponse({"ok": False, "message": message, "errors": errors or {}}, status=status)


# --- listing ----------------------------------------------------------------------------

@login_required
@require_GET
def quotation_list(request):
    today = date.today()
    start_raw, end_raw = request.GET.get("start_date"), request.GET.get("end_date")
    start = services.parse_date(start_raw) if start_raw else today
    end = services.parse_date(end_raw) if end_raw else today
    error = ""
    if start is None or end is None:
        error = "Enter valid start and end dates."
        start, end = start or today, end or today
    elif start > end:
        error = "Start Date cannot be later than End Date."
    search = (request.GET.get("q") or "").strip()[:50]
    rows = [] if error else services.list_quotations(start, end, search)
    page = Paginator(rows, services.PAGE_SIZE).get_page(request.GET.get("page"))
    can_edit = _can_edit(request.user)
    return render(request, "quotation_spearpart/quotation_spearpart_list.html", {
        "page": page, "rows": page.object_list, "start_date": start, "end_date": end, "search": search,
        "filter_error": error, "can_edit": can_edit,
        "selected": (request.GET.get("selected") or "").strip(),
    })


# --- entry form -------------------------------------------------------------------------

def _entry(request, mode, quot_no=None):
    can_edit = _can_edit(request.user)
    if mode != "view" and not can_edit:
        messages.error(request, "Saving to the SP_MACHINE database is switched off.")
        return redirect("quotation_spearpart:list")
    if mode == "add":
        data = services.blank_quotation()
    else:
        data = services.get_quotation(quot_no)
        if not data:
            raise Http404("Quotation not found.")
    return render(request, "quotation_spearpart/quotation_spearpart_entry.html", {
        "mode": mode,
        "quotation": data,
        "form_config": {
            "mode": mode,
            "token": services.new_token(),
            "quotation": data,
            "urls": {
                "save": reverse("quotation_spearpart:api_save"),
                "parties": reverse("quotation_spearpart:api_parties"),
                "items": reverse("quotation_spearpart:api_items"),
                "list": reverse("quotation_spearpart:list"),
                "edit": reverse("quotation_spearpart:edit", args=["__NO__"]),
                "print": reverse("quotation_spearpart:print", args=["__NO__"]),
            },
            "can_confirm": mode != "view" and can_edit,
        },
    })


@login_required
@require_GET
def quotation_add(request):
    return _entry(request, "add")


@login_required
@require_GET
def quotation_edit(request, quot_no):
    return _entry(request, "edit", quot_no)


@login_required
@require_GET
def quotation_view(request, quot_no):
    return _entry(request, "view", quot_no)


# --- JSON APIs --------------------------------------------------------------------------

@login_required
@require_GET
def api_parties(request):
    return JsonResponse({"parties": services.search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def api_items(request):
    return JsonResponse({"items": services.search_items(request.GET.get("q", ""))})


@login_required
@require_POST
def api_save(request):
    """Body: {"token", "action": "save" | "confirm", "key": <existing quot no or null>, "quotation": {...}}."""
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return _json_error("Invalid request.")
    if not isinstance(body, dict):
        return _json_error("Invalid request.")
    key = body.get("key") or None
    action = body.get("action") if body.get("action") in ("save", "confirm") else "save"
    if not _can_edit(request.user):
        return _json_error("You don't have permission to save quotations.", status=403)
    try:
        result = services.run_once(
            body.get("token"), action, request.user,
            lambda: services.save_quotation(body.get("quotation"), key=key, user=request.user, confirm=action == "confirm"),
        )
    except (QuotationSparepartError, _TokenError) as exc:
        return _json_error(str(exc), status=getattr(exc, "status", 400), errors=getattr(exc, "errors", {}))
    if action == "confirm":
        messages.success(request, result["message"])
    return JsonResponse({
        "ok": True, **result,
        "next_token": services.new_token(),
        "edit_url": reverse("quotation_spearpart:edit", args=[result["quot_no"]]),
        "list_url": reverse("quotation_spearpart:list") + f"?selected={result['quot_no']}",
    })


@login_required
@require_POST
def quotation_delete(request, quot_no):
    if not _can_edit(request.user):
        messages.error(request, "You don't have permission to delete quotations.")
        return redirect("quotation_spearpart:list")
    try:
        result = services.delete_quotation(quot_no)
    except QuotationSparepartError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, result["message"])
    back = request.POST.get("next") or ""
    if not back.startswith(reverse("quotation_spearpart:list")):
        back = reverse("quotation_spearpart:list")
    return redirect(back)


# --- printing ---------------------------------------------------------------------------

@login_required
@require_GET
def quotation_print(request, quot_no):
    data = services.get_quotation(quot_no)
    if not data:
        raise Http404("Quotation not found.")
    return render(request, "quotation_spearpart/quotation_spearpart_print.html", {
        "q": data, "brand_name": settings.BRAND["name"].upper(),
        "autoprint": request.GET.get("autoprint") == "1",
    })

"""Quotation views -- listing, entry (add / modify / view), save / confirm / delete, print."""
import json
from datetime import date
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from . import services
from .services import QuotationError


def _require(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _perms(user):
    writes = services.writes_enabled()
    return {
        "add": writes and user.has_perm(services.ADD_PERMISSION),
        "change": writes and user.has_perm(services.CHANGE_PERMISSION),
        "delete": writes and user.has_perm(services.DELETE_PERMISSION),
    }


def _json_error(message, status=400, errors=None):
    return JsonResponse({"ok": False, "message": message, "errors": errors or {}}, status=status)


# --- listing ----------------------------------------------------------------------------

@login_required
@require_GET
def quotation_list(request):
    _require(request.user, services.VIEW_PERMISSION)
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
    return render(request, "quotations/quotation_list.html", {
        "page": page, "rows": page.object_list, "start_date": start, "end_date": end, "search": search,
        "filter_error": error, "perms_q": _perms(request.user),
        "selected": (request.GET.get("selected") or "").strip(),
    })


# --- entry form -------------------------------------------------------------------------

def _entry(request, mode, quot_no=None):
    if mode == "view":
        _require(request.user, services.VIEW_PERMISSION)
    elif mode == "add":
        _require(request.user, services.ADD_PERMISSION)
    else:
        _require(request.user, services.CHANGE_PERMISSION)
    if mode != "view":
        if not services.writes_enabled():
            messages.error(request, "Saving to the SP_MACHINE database is switched off.")
            return redirect("quotations:list")
    if mode == "add":
        data = services.blank_quotation()
    else:
        data = services.get_quotation(quot_no)
        if not data:
            raise Http404("Quotation not found.")
    return render(request, "quotations/quotation_entry.html", {
        "mode": mode,
        "quotation": data,
        "form_config": {
            "mode": mode,
            "token": services.new_token(),
            "quotation": data,
            "currencies": list(services.CURRENCIES),
            "default_currency": services.DEFAULT_CURRENCY,
            "urls": {
                "save": reverse("quotations:api_save"),
                "parties": reverse("quotations:api_parties"),
                "items": reverse("quotations:api_items"),
                "list": reverse("quotations:list"),
                "edit": reverse("quotations:edit", args=["__NO__"]),
                "print": reverse("quotations:print", args=["__NO__"]),
            },
            "can_confirm": mode != "view" and _perms(request.user)["change" if mode == "edit" else "add"],
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
    _require(request.user, services.VIEW_PERMISSION)
    return JsonResponse({"parties": services.search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def api_items(request):
    _require(request.user, services.VIEW_PERMISSION)
    return JsonResponse({"items": services.search_items(request.GET.get("q", ""))})


@login_required
@require_POST
def api_save(request):
    """
    Body: {"token", "action": "save" | "confirm", "key": <existing quot no or null>, "quotation": {...}}.
    Add needs the add permission, modify the change permission. The token makes a
    repeated submit return the first result instead of saving twice.
    """
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return _json_error("Invalid request.")
    if not isinstance(body, dict):
        return _json_error("Invalid request.")
    key = body.get("key") or None
    action = body.get("action") if body.get("action") in ("save", "confirm") else "save"
    perm = services.ADD_PERMISSION if key is None else services.CHANGE_PERMISSION
    if not request.user.has_perm(perm):
        return _json_error("You don't have permission to save quotations.", status=403)
    try:
        result = services.run_once(
            body.get("token"), action, request.user,
            lambda: services.save_quotation(body.get("quotation"), key=key, user=request.user, confirm=action == "confirm"),
        )
    except QuotationError as exc:
        return _json_error(str(exc), status=exc.status, errors=exc.errors)
    if action == "confirm":
        messages.success(request, result["message"])  # shown on the list page Confirm returns to
    return JsonResponse({
        "ok": True, **result,
        "next_token": services.new_token(),
        "edit_url": reverse("quotations:edit", args=[result["quot_no"]]),
        "list_url": reverse("quotations:list") + f"?selected={result['quot_no']}",
    })


@login_required
@require_POST
def quotation_delete(request, quot_no):
    if not request.user.has_perm(services.DELETE_PERMISSION):
        raise PermissionDenied
    try:
        result = services.delete_quotation(quot_no)
    except QuotationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, result["message"])
    back = request.POST.get("next") or ""
    if not back.startswith(reverse("quotations:list")):
        back = reverse("quotations:list")
    return redirect(back)


# --- printing ---------------------------------------------------------------------------

def _print_context(request, quot_no):
    _require(request.user, services.VIEW_PERMISSION)
    data = services.get_quotation(quot_no)
    if not data:
        raise Http404("Quotation not found.")
    return {"q": data, "brand_name": settings.BRAND["name"].upper()}


@login_required
@require_GET
def quotation_print(request, quot_no):
    context = _print_context(request, quot_no)
    context["autoprint"] = request.GET.get("autoprint") == "1"
    return render(request, "quotations/quotation_print.html", context)


def _pdf_static_link_callback(uri, rel):
    """xhtml2pdf can't fetch over HTTP: map a STATIC_URL link (the logo) to its file."""
    from django.contrib.staticfiles import finders

    if uri.startswith(settings.STATIC_URL):
        path = finders.find(uri[len(settings.STATIC_URL):].split("?")[0])
        if path:
            return path
    return uri


@login_required
@require_GET
def quotation_pdf(request, quot_no):
    from xhtml2pdf import pisa

    context = _print_context(request, quot_no)
    html = render(request, "quotations/quotation_pdf.html", context).content.decode("utf-8")
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, link_callback=_pdf_static_link_callback)
    if result.err:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Quotation_{context["q"]["quot_no"]}.pdf"'
    return response

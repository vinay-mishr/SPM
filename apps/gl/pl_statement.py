"""Accounts > Final Accounts > P & L (Cl Stock) (VFP "PROFIT & LOSS
STATEMENT" form).

The entire pasted VFP source for this screen is one line:

    do trade1 with thisform.trundate.value, thisform.tclstk.value, thisform.tgpper.Value

i.e. the actual Profit & Loss computation lives in a ``trade1`` procedure
that was never pasted -- not its report layout, not which ``trans``/
``gled_mst`` rows it reads, not how G.P.% or Closing Stock factor into the
P&L figure. There is nothing here to confirm against (unlike every other
screen in this app, where at least the report body or an Excel export block
was given). Guessing a Profit & Loss calculation from a one-line call with
no body would be exactly the kind of unverified-financial-write/compute
this project's standing rule exists to prevent.

The input form itself (G.P.%, CLOSING STOCK, RUN DATE, VIEW, EXIT) is built
and wired to a real endpoint, matching the screenshot -- but that endpoint
returns a clear explanation instead of a guessed P&L figure. Ask for the
``trade1`` procedure's own source (or the legacy P&L report layout) before
this can be implemented for real.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView


class PlStatementView(LoginRequiredMixin, TemplateView):
    template_name = "gl/pl_statement.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"run_date": date.today().isoformat()}
        return context


@login_required
@require_POST
def pl_view(request):
    import json

    try:
        payload = json.loads(request.body or "{}")
    except ValueError:
        payload = {}

    try:
        date.fromisoformat(payload.get("run_date"))
    except (TypeError, ValueError):
        return JsonResponse({"message": "Enter a valid Run Date."}, status=400)
    try:
        Decimal(str(payload.get("gp_percent") or "0"))
        Decimal(str(payload.get("closing_stock") or "0"))
    except Exception:
        return JsonResponse({"message": "Enter valid numeric G.P.% and Closing Stock values."}, status=400)

    return JsonResponse({
        "message": (
            "P & L (Cl Stock) is not implemented yet: the VFP source for this screen is a single "
            "call to a \"trade1\" procedure whose own logic (how G.P.%, Closing Stock, and Run Date "
            "combine with the trans/gled_mst data into a Profit & Loss statement) was never provided. "
            "Share the trade1 procedure's source or the legacy P&L report layout to implement this for real."
        ),
    }, status=501)

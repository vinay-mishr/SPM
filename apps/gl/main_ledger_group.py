"""Accounts > Ledger Printing > Main Ledger Group Wise (VFP "LEDGER
PRINTING" / group-scoped "MAIN LEDGER" report).

Same per-ledger block as apps.gl.main_ledger's own "MAIN LEDGER"
(``apps.gl.main_ledger.ledger_block`` -- identical opening-balance formula,
running-balance sign convention, and "only shown if it has a non-zero
opening balance or a transaction in range" rule, reused unchanged), just
scoped to every ``gled_mst`` account whose ``gl_type`` matches one GROUP
picked via the GROUP field's lookup (``group1.grp_code``/``grp_name`` --
not previously used anywhere else in this app; confirmed only from the
pasted VFP source itself, not guessed).

Ledgers are iterated in ``gcode`` order (the VFP source's own
``use gled_mst in 0 orde gcode`` + ``scan for allt(gl_type)==...``), unlike
plain Main Ledger's ALL mode, which orders by ``gdesc``.
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .cash_entry import _clean, _rows
from .main_ledger import ledger_block


def _fy_start(today):
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def search_groups(q):
    q = (q or "").strip().upper()
    if q:
        rows = _rows(
            "SELECT grp_code, grp_name FROM group1 WHERE UPPER(grp_code) LIKE %s OR UPPER(grp_name) LIKE %s ORDER BY grp_name",
            [f"%{q}%", f"%{q}%"],
        )
    else:
        rows = _rows("SELECT grp_code, grp_name FROM group1 ORDER BY grp_name")
    return [{"code": _clean(r["grp_code"]), "name": _clean(r["grp_name"]) or ""} for r in rows[:20]]


def main_ledger_group_blocks(grp_code, start, end):
    blocks = []
    for led in _rows("SELECT gcode, gdesc FROM gled_mst WHERE gl_type = %s ORDER BY gcode", [grp_code]):
        block = ledger_block(_clean(led["gcode"]), _clean(led["gdesc"]) or "", start, end)
        if block:
            blocks.append(block)
    return blocks


class MainLedgerGroupView(LoginRequiredMixin, TemplateView):
    template_name = "gl/main_ledger_group.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": _fy_start(today).isoformat(), "end_date": today.isoformat()}
        return context


def _params(request):
    def parse(value, default):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return default

    today = date.today()
    grp_code = (request.GET.get("grp_code") or "").strip()
    start = parse(request.GET.get("start_date"), _fy_start(today))
    end = parse(request.GET.get("end_date"), today)
    return grp_code, start, end


@login_required
@require_GET
def mlg_groups(request):
    return JsonResponse({"groups": search_groups(request.GET.get("q", ""))})


@login_required
@require_GET
def mlg_data(request):
    grp_code, start, end = _params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    if not grp_code:
        return JsonResponse({"message": "Select a Group."}, status=400)
    return JsonResponse({
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "blocks": main_ledger_group_blocks(grp_code, start, end),
    })

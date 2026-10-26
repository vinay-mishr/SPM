"""Accounts > Ledger Printing > Ledger Groupwise (VFP "LEDGER" report).

Not to be confused with apps.gl.main_ledger_group's own "Main Ledger Group
Wise" (that one filters by a single ``gled_mst.gl_type`` GROUP code) -- this
is a different VFP screen entirely: a grid of every ``gled_mst`` account
(SEARCH filters it to those whose ``gdesc`` starts with the typed text, the
VFP source's own ``left(gdesc,len(...))==...``), each with a tick-box
("FLAG" column -- TAG ALL / UNTAG ALL / per-row toggle), and VIEW renders
one block per TICKED ledger for the date range -- i.e. an arbitrary,
user-picked set of ledgers shown together, not a GL group.

The per-ledger block itself (opening balance, running balance sign
convention, the "only shown if it has a non-zero opening balance or a
transaction in range" rule) is identical to apps.gl.main_ledger's own
"MAIN LEDGER", and reuses its ``ledger_block`` helper unchanged.

The VFP source's own ``thisform.div`` branch ('SE'/'AP'/'VS'/'VI', each
reading a different ``trans``/``trans2``/``trans1``/``trans3`` table) is the
same multi-dataset switch already flagged (not reproduced) in
apps.gl.journal_book's own docstring -- this project only has the one
``trans`` table every other screen here already uses.
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from .cash_entry import _clean, _rows
from .main_ledger import ledger_block


def _fy_start(today):
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def search_ledger_rows(name_prefix):
    name_prefix = (name_prefix or "").strip()
    if name_prefix:
        rows = _rows(
            "SELECT gcode, gdesc FROM gled_mst WHERE UPPER(gdesc) LIKE %s ORDER BY gdesc",
            [f"{name_prefix.upper()}%"],
        )
    else:
        rows = _rows("SELECT gcode, gdesc FROM gled_mst ORDER BY gdesc")
    return [{"code": _clean(r["gcode"]), "desc": _clean(r["gdesc"]) or ""} for r in rows]


class LedgerGroupwiseView(LoginRequiredMixin, TemplateView):
    template_name = "gl/ledger_groupwise.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": _fy_start(today).isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def lg_rows(request):
    return JsonResponse({"rows": search_ledger_rows(request.GET.get("name", ""))})


@login_required
@require_POST
def lg_data(request):
    import json

    def parse_date(value, default):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return default

    try:
        payload = json.loads(request.body or "{}")
    except ValueError:
        payload = {}

    today = date.today()
    start = parse_date(payload.get("start_date"), _fy_start(today))
    end = parse_date(payload.get("end_date"), today)
    codes = [(_clean(c) or "") for c in (payload.get("codes") or [])]
    codes = [c for c in codes if c]

    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    if not codes:
        return JsonResponse({"message": "Tag at least one ledger."}, status=400)

    descs = {_clean(r["gcode"]): _clean(r["gdesc"]) or "" for r in _rows(
        f"SELECT gcode, gdesc FROM gled_mst WHERE gcode IN ({','.join(['%s'] * len(codes))})", codes,
    )}
    blocks = []
    for code in codes:
        block = ledger_block(code, descs.get(code, ""), start, end)
        if block:
            blocks.append(block)
    return JsonResponse({"start_date": start.isoformat(), "end_date": end.isoformat(), "blocks": blocks})

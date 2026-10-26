"""Accounts > Book Printing > Bank Book (VFP "BANK BOOK" report).

Direct port of the pasted ``bankbook.PRN`` report -- identical shape to
apps.gl.journal_book ("JOURNAL BOOK"), just scoped to ``ttype = 'BV'``
(apps.gl.bank_entry's own voucher type) instead of 'JV': every matching
line in the date range is listed in order (no opening/running balance, no
``tcode <>`` exclusion), with one grand DEBIT/CREDIT total for the whole
report. Account description resolution (party + city via ``tccode``/
``cust_mst``, else ``gled_mst.gdesc``) and the "To "/"By " narration prefix
convention are identical to apps.gl.journal_book / apps.gl.cash_book /
apps.gl.voucher_printing.

Deterministic order: ``tdate`` then ``tdoc`` (voucher number), same
tie-breaker the other Book Printing reports already use.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .cash_entry import _clean, _d, _rows


def _fy_start(today):
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def bank_book_lines(start, end):
    rows = []
    total_debit = total_credit = Decimal("0")
    for r in _rows(
        "SELECT t.tdate, t.tdoc, t.tdbcr, t.tamt, t.tnar1, t.tccode, g.gdesc, c.cname, c.cadd3 "
        "FROM trans t LEFT JOIN gled_mst g ON g.gcode = t.tcode "
        "LEFT JOIN cust_mst c ON c.ccode = t.tccode "
        "WHERE t.ttype = 'BV' AND t.tdate >= %s AND t.tdate <= %s "
        "ORDER BY t.tdate, t.tdoc",
        [start, end],
    ):
        tccode = _clean(r["tccode"])
        if tccode:
            city = _clean(r["cadd3"]) or ""
            account = (_clean(r["cname"]) or "PARTY NOT FOUND") + (f", {city}" if city else "")
        else:
            account = _clean(r["gdesc"]) or "ACCOUNT NOT FOUND"
        narration = _clean(r["tnar1"]) or ""
        amt = _d(r["tamt"])
        tdbcr = _clean(r["tdbcr"])
        if tdbcr == "D":
            total_debit += amt
            debit, credit = f"{amt:.2f}", ""
        else:
            total_credit += amt
            debit, credit = "", f"{amt:.2f}"
        rows.append({
            "date": r["tdate"].isoformat(), "account": account, "narration": narration,
            "prefix": "To" if tdbcr == "D" else "By",
            "debit": debit, "credit": credit,
        })
    return rows, f"{total_debit:.2f}", f"{total_credit:.2f}"


class BankBookView(LoginRequiredMixin, TemplateView):
    template_name = "gl/bank_book.html"

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
    start = parse(request.GET.get("start_date"), _fy_start(today))
    end = parse(request.GET.get("end_date"), today)
    return start, end


@login_required
@require_GET
def bb_data(request):
    start, end = _params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    lines, total_debit, total_credit = bank_book_lines(start, end)
    return JsonResponse({
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "lines": lines, "total_debit": total_debit, "total_credit": total_credit,
    })

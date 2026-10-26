"""Accounts > Book Printing > Combined Book (VFP "COMBINED BOOK" report).

Identical structure to apps.gl.cash_book's "CASH BOOK" (same opening-balance
formula, same per-day OPENING/CLOSING blocks, same running-balance sign
convention, same "a day with nothing prints nothing" behaviour) -- the only
difference, confirmed line-by-line against the pasted VFP source, is that
Combined Book's own movement filter drops Cash Book's ``ttype = 'CV'``
restriction: it's every voucher type (CV/BV/JV) whose ``tcode`` isn't the
Cash ledger itself, not just Cash Entry vouchers. See apps.gl.cash_book's
own docstring for the full formula write-up; only the one filter differs
here, so it isn't repeated.

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

from .cash_entry import CASH_LEDGER_CODE, _clean, _d, _rows


def _fy_start(today):
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def _opening_balance(start):
    cash = _rows("SELECT gyob FROM gled_mst WHERE gcode = %s", [CASH_LEDGER_CODE])
    balance = _d(cash[0]["gyob"]) if cash else Decimal("0")
    for r in _rows(
        "SELECT tdbcr, SUM(tamt) AS total FROM trans WHERE tcode = %s AND tdate < %s GROUP BY tdbcr",
        [CASH_LEDGER_CODE, start],
    ):
        if _clean(r["tdbcr"]) == "D":
            balance += _d(r["total"])
        elif _clean(r["tdbcr"]) == "C":
            balance -= _d(r["total"])
    return balance


def _side(balance):
    return "Dr." if balance > 0 else "Cr." if balance < 0 else ""


def combined_book_days(start, end):
    by_day = {}
    for r in _rows(
        "SELECT t.tdate, t.tdoc, t.tdbcr, t.tamt, t.tnar1, t.tccode, g.gdesc, c.cname, c.cadd3 "
        "FROM trans t LEFT JOIN gled_mst g ON g.gcode = t.tcode "
        "LEFT JOIN cust_mst c ON c.ccode = t.tccode "
        "WHERE t.tcode <> %s AND t.tdate >= %s AND t.tdate <= %s "
        "ORDER BY t.tdate, t.tdoc",
        [CASH_LEDGER_CODE, start, end],
    ):
        by_day.setdefault(r["tdate"], []).append(r)

    balance = _opening_balance(start)
    days = []
    for day in sorted(by_day):
        lines = by_day[day]
        opening_balance = balance
        total_debit = total_credit = Decimal("0")
        out_lines = []
        for r in lines:
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
                balance -= amt
                total_debit += amt
                debit, credit = f"{amt:.2f}", ""
            else:
                balance += amt
                total_credit += amt
                debit, credit = "", f"{amt:.2f}"
            out_lines.append({
                "account": account, "narration": narration,
                "prefix": "To" if tdbcr == "D" else "By",
                "debit": debit, "credit": credit,
            })
        days.append({
            "date": day.isoformat(),
            "opening_balance": f"{abs(opening_balance):.2f}", "opening_side": _side(opening_balance),
            "lines": out_lines,
            "total_debit": f"{total_debit:.2f}", "total_credit": f"{total_credit:.2f}",
            "closing_balance": f"{abs(balance):.2f}", "closing_side": _side(balance),
        })
    return days


class CombinedBookView(LoginRequiredMixin, TemplateView):
    template_name = "gl/combined_book.html"

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
def comb_data(request):
    start, end = _params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "days": combined_book_days(start, end),
    })

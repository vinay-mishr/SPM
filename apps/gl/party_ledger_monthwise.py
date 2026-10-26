"""Accounts > Ledger Printing > Party Ledger Monthwise (VFP "PARTY LEDGER
MONTHWISE" report).

The pasted VFP source for this screen included two blocks: a large
``posparty.PRN`` report (headed "PARTY WISE OUTSTANDING", a bill-aging
report by Dr./Cr. note and 30/60/90-day buckets) and an OLE-Excel export
block headed "PARTY LEDGER MONTHWISE". The screenshot's own form only has
PARTY, RUN DATE, EXCEL and EXIT -- no VIEW, no bill/ageing columns -- which
matches the Excel block, not ``posparty.PRN``. That PRN report is therefore
NOT reproduced here (flagged, not guessed into this screen); if it's wanted
too, it's a separate "Party Wise Outstanding" screen.

For the one selected party, one row per month of the financial year RUN
DATE falls in (``pfyfrom``..``pfyto`` -- April to March, apps.gl.cash_book's
own ``_fy_start`` convention, extended to a fiscal-year END here since nothing
else in this app has needed one yet): Opening Balance, Debit, Credit, Closing
Balance, each month's closing balance carried forward as the next month's
opening. Debit/Credit are summed from ``trans`` for that party's own
``tccode``, filtered by month+year of ``tdate`` -- the same ledger-posting
table and tccode convention apps.gl.party_ledger already uses, just grouped
by calendar month instead of by date range.

Months AFTER RUN DATE are listed (so every month of the financial year
always appears) but left with blank Opening/Debit/Credit/Closing -- exactly
matching the VFP source's own ``IF mdt<=thisform.trundate.Value`` guard,
which only fills those four cells for months up to and including RUN DATE.

RUN DATE must fall within the financial year (``pfyfrom``..``pfyto`` --
the VFP source's own validation rule, reproduced server-side here); its
own FY determines which 12 months get listed, not necessarily the
current one.
"""
from datetime import date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .cash_entry import _clean, _d, _rows, search_parties

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fy_bounds(run_date):
    fy_start_year = run_date.year if run_date.month >= 4 else run_date.year - 1
    fy_start = date(fy_start_year, 4, 1)
    fy_end = date(fy_start_year + 1, 3, 31)
    return fy_start, fy_end


def _fy_start_today(today):
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def _month_list(fy_start):
    months = []
    y, m = fy_start.year, fy_start.month
    for _ in range(12):
        months.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def party_ledger_monthwise_rows(ccode, run_date):
    fy_start, fy_end = _fy_bounds(run_date)
    party = _rows("SELECT cyob FROM cust_mst WHERE ccode = %s", [ccode])
    opening = _d(party[0]["cyob"]) if party else _d(0)

    rows = []
    for month_start in _month_list(fy_start):
        label = f"{MONTH_NAMES[month_start.month - 1]}'{month_start.year}"
        if month_start > run_date:
            rows.append({"month": label, "opening": "", "debit": "", "credit": "", "closing": ""})
            continue

        debit = credit = _d(0)
        for r in _rows(
            "SELECT tdbcr, SUM(tamt) AS total FROM trans "
            "WHERE tccode = %s AND MONTH(tdate) = %s AND YEAR(tdate) = %s GROUP BY tdbcr",
            [ccode, month_start.month, month_start.year],
        ):
            if _clean(r["tdbcr"]) == "D":
                debit = _d(r["total"])
            elif _clean(r["tdbcr"]) == "C":
                credit = _d(r["total"])

        closing = opening + debit - credit
        rows.append({
            "month": label, "opening": f"{opening:.2f}", "debit": f"{debit:.2f}",
            "credit": f"{credit:.2f}", "closing": f"{closing:.2f}",
        })
        opening = closing

    return rows, fy_start, fy_end


class PartyLedgerMonthwiseView(LoginRequiredMixin, TemplateView):
    template_name = "gl/party_ledger_monthwise.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        fy_start = _fy_start_today(today)
        context["initial_data"] = {
            "run_date": today.isoformat(),
            "fy_start": fy_start.isoformat(), "fy_end": date(fy_start.year + 1, 3, 31).isoformat(),
        }
        return context


@login_required
@require_GET
def plmw_parties(request):
    return JsonResponse({"parties": search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def plmw_export(request):
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font

    ccode = (request.GET.get("ccode") or "").strip()
    try:
        run_date = date.fromisoformat(request.GET.get("run_date"))
    except (TypeError, ValueError):
        run_date = date.today()

    if not ccode:
        return JsonResponse({"message": "Select a party."}, status=400)

    party = _rows("SELECT cname FROM cust_mst WHERE ccode = %s", [ccode])
    party_name = _clean(party[0]["cname"]) if party else ""

    rows, fy_start, fy_end = party_ledger_monthwise_rows(ccode, run_date)
    if not (fy_start <= run_date <= fy_end):
        return JsonResponse({"message": "Run Date must fall within the financial year."}, status=400)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([settings.BRAND["name"].upper()])
    ws.append([settings.BRAND.get("address_line1", "")])
    ws.append([f"AS ON DATE {run_date:%d/%m/%Y}"])
    ws.append([f"PARTY : {party_name}"])
    header_row = ws.max_row + 1
    ws.append(["Month", "Op.Balance", "Debit", "Credit", "Cl.Balance"])
    for c in ws[header_row]:
        c.font = Font(bold=True)
    for w, col in zip([15, 12, 12, 12, 12], "ABCDE"):
        ws.column_dimensions[col].width = w

    for r in rows:
        ws.append([
            r["month"],
            float(r["opening"]) if r["opening"] else None,
            float(r["debit"]) if r["debit"] else None,
            float(r["credit"]) if r["credit"] else None,
            float(r["closing"]) if r["closing"] else None,
        ])

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Party_Ledger_Monthwise_{run_date:%d-%m-%Y}.xlsx"'
    return response

"""GST Reports > Business to Consumer Small (VFP "B2CS" form).

Direct port of the pasted VFP B2CS(7) Excel-export block. Same ``bill``/
``i_master`` tables and ``bill_type = 'G'`` convention as
apps.gst_invoice.b2b_report/b2cl_report (see their own docstrings).

A bill counts as B2CS when it's a GST bill for an UNREGISTERED recipient
(``gst_no`` empty) that is either interstate and small (``cstat = 'I'`` AND
``n_amount <= 250000``) or an export (``cstat = 'W'``), AND is either a cash
sale (``ca_cr = 'CA'``) or UNREGISTERED category (``cat_cd = '03'``, see
apps.gst_invoice.b2b_report's own note on these codes) -- preserved exactly
from the VFP source's own compound filter.

Each matching bill contributes one Excel row PER TAX RATE, grouped the same
"do while gst==mgst" way as B2B, summing (amount - dis_amt) same as B2B.
Invoice Type is 'E' (export) when the bill's ``cat_cd = '04'``, else 'OE'
(other than export) -- read straight from the VFP source's own IF/ELSE, not
reinterpreted.

The VFP source's own Summary block only ever writes Total Taxable Value
(``OleApp.Cells(3,4)``) -- its No. of Invoices / Total Invoice Value /
distinct-GSTIN lines are commented out, so only Total Taxable Value is kept
here. Cess has no column read anywhere in the VFP source, so it's always 0.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .services import BILL_TYPE, _clean, _d, _rows

MAX_INVOICE_VALUE = Decimal("250000")
EXPORT_CATEGORY_CODE = "04"


def b2cs_rows(start, end):
    bills = _rows(
        "SELECT bill_no, cat_cd, stname FROM bill WHERE bill_type = %s "
        "AND ((cstat = 'I' AND n_amount <= %s) OR cstat = 'W') "
        "AND (ca_cr = 'CA' OR cat_cd = '03') AND (gst_no IS NULL OR LTRIM(RTRIM(gst_no)) = '') "
        "AND b_date >= %s AND b_date <= %s ORDER BY b_date, bill_no",
        [BILL_TYPE, MAX_INVOICE_VALUE, start, end],
    )

    rows = []
    taxable_total = Decimal("0")

    for b in bills:
        bill_no = _clean(b["bill_no"])
        invoice_type = "E" if _clean(b["cat_cd"]) == EXPORT_CATEGORY_CODE else "OE"
        place_of_supply = _clean(b["stname"]) or ""

        lines = _rows(
            "SELECT gst, amount, dis_amt FROM i_master WHERE bill_no = %s AND bill_type = %s AND gst > 0 "
            "ORDER BY gst",
            [bill_no, BILL_TYPE],
        )
        by_rate = {}
        for l in lines:
            rate = _d(l["gst"])
            by_rate[rate] = by_rate.get(rate, Decimal("0")) + _d(l["amount"]) - _d(l["dis_amt"])

        for rate in sorted(by_rate):
            taxable_value = by_rate[rate]
            taxable_total += taxable_value
            rows.append({
                "invoice_type": invoice_type, "place_of_supply": place_of_supply,
                "rate": f"{rate:.2f}", "taxable_value": f"{taxable_value:.2f}",
            })

    totals = {"taxable_value": f"{taxable_total:.2f}"}
    return rows, totals


class B2csReportView(LoginRequiredMixin, TemplateView):
    template_name = "gst_invoice/b2cs_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


def _params(request):
    def parse(value, default):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return default

    today = date.today()
    start = parse(request.GET.get("start_date"), today)
    end = parse(request.GET.get("end_date"), today)
    return start, end


@login_required
@require_GET
def b2cs_export(request):
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font

    start, end = _params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)

    rows, totals = b2cs_rows(start, end)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    ws.append(["Summary For B2CS(7)"])
    ws["A1"].font = Font(bold=True, size=11)
    ws.append(["", "", "", "Total Taxable Value", "Total Cess"])
    for c in ws[2]:
        c.font = Font(bold=True, size=11)
    ws.append(["", "", "", float(totals["taxable_value"]), 0])
    ws.append([])

    header = ["Invoice Type", "Place of Supply", "RATE", "Taxable Value", "Cess Amount", "E-COMMERCE GSTIN"]
    widths = [21, 30, 6, 21, 13, 25]
    ws.append(header)
    header_row = ws.max_row
    for c in ws[header_row]:
        c.alignment = c.alignment.copy(horizontal="center", vertical="center", wrap_text=True)
        c.font = Font(bold=True, size=11)
    for w, col in zip(widths, "ABCDEF"):
        ws.column_dimensions[col].width = w

    for r in rows:
        ws.append([r["invoice_type"], r["place_of_supply"], float(r["rate"]), float(r["taxable_value"]), None, ""])
        for col in ("C", "D"):
            ws[f"{col}{ws.max_row}"].number_format = "0.00"

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="B2CS_{start:%d-%m-%Y}_to_{end:%d-%m-%Y}.xlsx"'
    return response

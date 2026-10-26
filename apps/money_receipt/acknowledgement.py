"""Money Receipt > Payment Acknowledgement (VFP "PAYMENT ACKNOWLEDGEMENT" form).

A thank-you letter for one specific receipt (``colh``), listing the bills it
settled (``col``, matched the same way apps.money_receipt.services already
does -- ``col.nar == colh.chq_no``), ported as a business letter (like
apps.purchase_orders's own "Pending Order Letter" -- see its
exports.build_pending_order_letter_workbook) rather than a plain table.

``cust_mst.cadd1``/``cadd2``/``cadd3`` (address lines 1/2/city) are this
project's own already-confirmed columns (apps.parties.models.Party /
apps.sale_order.services's own party-address lookups use the same three).
Company letterhead fields come from ``settings.BRAND`` -- the same source
apps.purchase_orders's own printed letters use -- standing in for the VFP
globals ``pcom``/``paddress``/``pcity``/``pphone`` (company
name/address/city/phone), which aren't DB-backed in the legacy source either.

Only EXCEL + EXIT are implemented, matching this screen's own screenshot
(no on-screen preview or PRN printing in the pasted source beyond the two
already-equivalent EXCEL/PRN layouts -- EXCEL is kept, PRN dropped, same
call already made for every other report in this app).
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .services import _clean, _d, _date, _rows


def party_receipts(party_code):
    """Every receipt (any mode) ever recorded for this party -- the VFP
    source's own list1 has no date/mode filter of its own."""
    rows = _rows(
        "SELECT chq_no, chq_dt, slip_dt, amount FROM colh WHERE p_code = %s ORDER BY slip_dt DESC",
        [party_code],
    )
    return [{
        "chq_no": _clean(r["chq_no"]) or "", "chq_dt": r["chq_dt"].isoformat() if r["chq_dt"] else "",
        "slip_dt": r["slip_dt"].isoformat() if r["slip_dt"] else "", "amount": f"{_d(r['amount']):.2f}",
    } for r in rows]


def acknowledgement_detail(party_code, chq_no, slip_dt_str):
    """Identified by (p_code, chq_no, slip_dt) -- services.get_receipt's own
    established key for this exact table (see its docstring: chq_dt is blank
    for CASH receipts, so the VFP source's own chq_no+chq_dt LOCATE can't
    tell two different CASH receipts apart; slip_dt can)."""
    slip_dt = _date(slip_dt_str)
    rows = _rows(
        "SELECT cname, cadd1, cadd2, cadd3 FROM cust_mst WHERE ccode = %s", [party_code],
    )
    if not rows:
        return None
    party = rows[0]
    header = _rows(
        "SELECT amount, chq_dt FROM colh WHERE p_code = %s AND chq_no = %s AND slip_dt = %s",
        [party_code, chq_no, slip_dt],
    )
    if not header:
        return None
    lines = _rows(
        "SELECT div, bill_no, b_date, b_amt, amount, c_dis, int_amt FROM col WHERE nar = %s AND p_code = %s",
        [chq_no, party_code],
    )
    return {
        "party_name": _clean(party["cname"]) or "",
        "address": [a for a in (_clean(party["cadd1"]), _clean(party["cadd2"]), _clean(party["cadd3"])) if a],
        "chq_no": chq_no, "chq_dt": header[0]["chq_dt"].isoformat() if header[0]["chq_dt"] else "",
        "amount": f"{_d(header[0]['amount']):.2f}",
        "lines": [
            {"div": _clean(l["div"]) or "", "bill_no": _clean(l["bill_no"]) or "",
             "bill_date": l["b_date"].isoformat() if l["b_date"] else "",
             "bill_amount": f"{_d(l['b_amt']):.2f}", "amount_received": f"{_d(l['amount']):.2f}",
             "cash_discount": f"{_d(l['c_dis']):.2f}", "interest_amt": f"{_d(l['int_amt']):.2f}",
             "balance": f"{(_d(l['b_amt']) - _d(l['amount']) - _d(l['c_dis']) + _d(l['int_amt'])):.2f}"}
            for l in lines
        ],
    }


class AcknowledgementView(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/acknowledgement.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"run_date": date.today().isoformat()}
        return context


@login_required
@require_GET
def ack_receipts(request):
    party = (request.GET.get("party_code") or "").strip().upper()
    if not party:
        return JsonResponse({"receipts": []})
    return JsonResponse({"receipts": party_receipts(party)})


@login_required
@require_GET
def ack_export(request):
    from io import BytesIO

    from django.conf import settings
    from openpyxl import Workbook
    from openpyxl.styles import Border, Font, Side

    party = (request.GET.get("party_code") or "").strip().upper()
    chq_no = (request.GET.get("chq_no") or "").strip()
    slip_dt = request.GET.get("slip_dt") or ""
    try:
        run_date = date.fromisoformat(request.GET.get("run_date") or "")
    except ValueError:
        run_date = date.today()

    data = acknowledgement_detail(party, chq_no, slip_dt)
    if not data:
        return JsonResponse({"message": "Party or receipt not found."}, status=404)

    wb = Workbook()
    ws = wb.active
    ws.title = "Payment Acknowledgement"
    font_name = "Arial"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    row = 1

    def write(r, value, bold=False, size=10):
        c = ws.cell(row=r, column=1, value=value or None)
        c.font = Font(name=font_name, size=size, bold=bold)
        return c

    write(row, settings.BRAND["name"], bold=True, size=14); row += 1
    write(row, settings.BRAND.get("address_line1", "")); row += 1
    write(row, settings.BRAND.get("address_line2", "") + " " + settings.BRAND.get("print_mobile", "")); row += 1
    row += 1
    write(row, f"{data['party_name']}                    DATE {run_date:%d/%m/%Y}", bold=True); row += 1
    for addr in data["address"]:
        write(row, addr); row += 1
    row += 1
    write(row, "Dear Sir,"); row += 2
    chq_dt_display = date.fromisoformat(data["chq_dt"]).strftime("%d/%m/%Y") if data["chq_dt"] else ""
    write(row, f"We thankfully acknowledge the receipt of your DD/Chq./Nft. Cash No.{data['chq_no']} "
               f"Dt.{chq_dt_display}"); row += 1
    write(row, f"Amount {data['amount']} as per the details given below."); row += 1
    row += 1

    header_row = row
    headers = [("INV. NO.", 10), ("INV. DATE", 12), ("INV.AMOUNT", 12), ("AMT.RECEIVED", 12),
               ("CASH DIS.", 10), ("INT.AMT.", 10)]
    for col, (label, width) in enumerate(headers, start=1):
        c = ws.cell(row=header_row, column=col, value=label)
        c.font = Font(name=font_name, size=10, bold=True)
        ws.column_dimensions[c.column_letter].width = width
    row += 1

    for l in data["lines"]:
        values = [l["div"] + l["bill_no"], date.fromisoformat(l["bill_date"]) if l["bill_date"] else None,
                  float(l["bill_amount"]), float(l["amount_received"]), float(l["cash_discount"]),
                  float(l["interest_amt"])]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.font = Font(name=font_name, size=10)
            if col == 2:
                cell.number_format = "dd/mm/yyyy"
            elif col > 2:
                cell.number_format = "0.00"
        row += 1

    for r in range(header_row, row):
        for c in range(1, len(headers) + 1):
            ws.cell(row=r, column=c).border = border

    row += 1
    write(row, "Yours Sincerely"); row += 1
    write(row, f"For {settings.BRAND['name']}"); row += 2
    write(row, "Authorized Signatory"); row += 1
    write(row, "Accounts Deptt.")

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Payment_Acknowledgement_{chq_no or "receipt"}.xlsx"'
    return response

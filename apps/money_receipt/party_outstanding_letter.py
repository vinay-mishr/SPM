"""Reports > Sales Reports > Party Outstanding Letter 1 (VFP "PARTY
OUTSTANDING LETTER" form, OLE-Excel export block).

One letter for a single, required party: every ``bill`` line with
``pmt_rcd = 'N'`` (exactly "N", not merely "not Y" like
apps.money_receipt.state_wise_outstanding's own filter -- a bill the VFP
source stamps some other status on, e.g. part-paid, is deliberately left
out of this letter) for that party, in the "SP" division (``pdv``, the
same project-wide division constant apps.gst_invoice.services.DIV already
uses), dated on or before RUN DATE.

Interest (column G) is a simple-interest grace-period formula read
verbatim off the VFP source: 0 before day 25 past ``gr_dt``
(Goods Receipt Date, not the bill's own date -- same convention
apps.money_receipt.state_wise_outstanding's aging already uses), then
21% p.a. on (balance) for every day past day 25:

    day_diff = RUN DATE - gr_dt
    interest = 0                                           if day_diff <= 25
             = balance * 21 * (day_diff - 25) / (100 * 365) otherwise

"AMOUNT RECEIVED" (column D) is NOT plain ``amt_rcd`` -- the VFP source
writes ``amt_rcd + int_amt - c_dis`` into that cell, preserved exactly
even though it reads more like a second balance-ish figure than a
receipt total. BALANCE (column E) is ``n_amount - amt_rcd + int_amt -
c_dis`` (note the sign: here ``int_amt`` ADDS and ``c_dis`` SUBTRACTS,
unlike apps.money_receipt.state_wise_outstanding's own balance formula,
which also subtracts ``c_note1``/adds ``d_note1`` -- this letter has no
such credit/debit-note netting at all). NET AMOUNT (column H) is balance
+ interest. The source's own TOTAL row sums BALANCE only (interest is
never summed into it), and -- preserved as written, not "fixed" -- that
TOTAL row's label lands in column E while its value lands in column F.

No row is skipped for a zero balance (unlike every other report in this
project's Sales Reports section): every bill matching the filter prints,
same as the VFP source's own unconditional ``scan``.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .services import _clean, _d, _rows

DIVISION = "SP"
GRACE_DAYS = 25
INTEREST_RATE = Decimal("21")


def party_outstanding_letter_rows(party_code, run_date):
    party = _rows("SELECT ccode, cname, cadd1, cadd2, cadd3 FROM cust_mst WHERE ccode = %s", [party_code])
    if not party:
        return None

    bills = _rows(
        "SELECT bill_no, b_date, n_amount, amt_rcd, int_amt, c_dis, gr_dt FROM bill "
        "WHERE pmt_rcd = 'N' AND b_date <= %s AND p_code = %s AND div = %s ORDER BY b_date",
        [run_date, party_code, DIVISION],
    )

    rows = []
    total_balance = Decimal("0")
    for b in bills:
        n_amount = _d(b["n_amount"])
        amt_rcd = _d(b["amt_rcd"])
        int_amt = _d(b["int_amt"])
        c_dis = _d(b["c_dis"])
        day_diff = (run_date - b["gr_dt"]).days if b["gr_dt"] else 0
        balance = n_amount - amt_rcd + int_amt - c_dis
        interest = Decimal("0")
        if day_diff > GRACE_DAYS:
            interest = balance * INTEREST_RATE * (day_diff - GRACE_DAYS) / (Decimal("100") * Decimal("365"))
        rows.append({
            "bill_no": _clean(b["bill_no"]) or "", "bill_date": b["b_date"].isoformat() if b["b_date"] else "",
            "invoice_amount": f"{n_amount:.2f}", "amount_received": f"{(amt_rcd + int_amt - c_dis):.2f}",
            "balance": f"{balance:.2f}", "day_over": day_diff, "interest": f"{interest:.2f}",
            "net_amount": f"{(balance + interest):.2f}",
        })
        total_balance += balance

    return {
        "party_code": party_code, "party_name": _clean(party[0]["cname"]) or "",
        "address_1": _clean(party[0]["cadd1"]) or "", "address_2": _clean(party[0]["cadd2"]) or "",
        "address_3": _clean(party[0]["cadd3"]) or "", "rows": rows, "total_balance": f"{total_balance:.2f}",
    }


class PartyOutstandingLetterView(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/party_outstanding_letter.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"run_date": date.today().isoformat()}
        return context


def _params(request):
    party_code = (request.GET.get("party_code") or "").strip().upper()
    try:
        run_date = date.fromisoformat(request.GET.get("run_date"))
    except (TypeError, ValueError):
        run_date = date.today()
    return party_code, run_date


@login_required
@require_GET
def pol_export(request):
    from io import BytesIO

    from django.conf import settings
    from openpyxl import Workbook
    from openpyxl.styles import Font

    party_code, run_date = _params(request)
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    data = party_outstanding_letter_rows(party_code, run_date)
    if data is None:
        return JsonResponse({"message": "Party not found."}, status=404)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([settings.BRAND["name"].upper()])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([])
    ws.append([f"{data['party_name']}DATE {run_date:%d/%m/%Y}"])
    ws.append([data["address_1"]])
    ws.append([data["address_2"]])
    ws.append([data["address_3"]])
    ws.append(["Sub. :- OUTSTANDING BILLS"])
    ws.append(["Dear Sir"])
    ws.append(["Given below are particulars of our ourtstanding bills as per our records"])
    ws.append(["Please note that payment of all overdue bills should be effected immediately."])
    ws.append(["Payment of remaining bills may please be made on due dates."])

    header = ["INV NO.", "INV DATE", "INV AMOUNT", "AMOUNT RECEIVED", "BALANCE", "D/OVER", "INT.AMOUNT",
               "NET AMOUNT"]
    widths = [6, 10, 12, 20, 15, 10, 12, 15]
    ws.append(header)
    header_row = ws.max_row
    for c in ws[header_row]:
        c.font = Font(bold=True)
    for w, col in zip(widths, "ABCDEFGH"):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["B"].number_format = "dd/mm/yy"

    for r in data["rows"]:
        ws.append([
            r["bill_no"], date.fromisoformat(r["bill_date"]) if r["bill_date"] else None,
            float(r["invoice_amount"]), float(r["amount_received"]), float(r["balance"]), r["day_over"],
            float(r["interest"]), float(r["net_amount"]),
        ])
        ws.cell(row=ws.max_row, column=3).number_format = "0.00"
        ws.cell(row=ws.max_row, column=4).number_format = "0.00"
        ws.cell(row=ws.max_row, column=5).number_format = "0.00"
        ws.cell(row=ws.max_row, column=7).number_format = "0.00"
        ws.cell(row=ws.max_row, column=8).number_format = "0.00"

    ws.append(["", "", "", "", "TOTAL", float(data["total_balance"])])
    ws.append([])
    ws.append([f"For {settings.BRAND['name'].upper()}"])
    ws.append([])
    ws.append(["Authorized Signatory"])
    ws.append(["Interest @21% will be charged after 60 days from the date of Invoice."])

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Party_Outstanding_Letter_{party_code}_{run_date:%d-%m-%Y}.xlsx"'
    return response

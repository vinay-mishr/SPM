"""Reports > Sales Reports > Party Outstanding Letter 2 (VFP "PARTY
OUTSTANDING LETTER" form, second variant, OLE-Excel export block).

Nearly identical to apps.money_receipt.party_outstanding_letter -- same
single required party, same RUN DATE, same letter header text -- with two
differences, both preserved exactly from this pasted source rather than
reconciled with Letter 1:
  * The bill filter is ``pmt_rcd <> 'Y'`` here (any status but fully
    paid), not Letter 1's exact ``pmt_rcd = 'N'``, and its division line
    (``set filt to allt(div)=allt(pdv)``) is commented out in the VFP
    source -- so this variant is NOT scoped to the "SP" division at all,
    unlike Letter 1.
  * Interest (``intamt``) is still computed with the same 25-day-grace,
    21% p.a. formula as Letter 1, but never written to any cell or
    totalled here -- the Excel block only ever has six columns (INV NO.,
    INV DATE, INV AMOUNT, AMOUNT RECEIVED, BALANCE, D/OVER), no INT.AMOUNT
    or NET AMOUNT column at all. Computed and dropped, exactly as written.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .services import _clean, _d, _rows


def party_outstanding_letter2_rows(party_code, run_date):
    party = _rows("SELECT ccode, cname, cadd1, cadd2, cadd3 FROM cust_mst WHERE ccode = %s", [party_code])
    if not party:
        return None

    bills = _rows(
        "SELECT bill_no, b_date, n_amount, amt_rcd, int_amt, c_dis, gr_dt FROM bill "
        "WHERE COALESCE(pmt_rcd, '') <> 'Y' AND b_date <= %s AND p_code = %s ORDER BY b_date",
        [run_date, party_code],
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
        rows.append({
            "bill_no": _clean(b["bill_no"]) or "", "bill_date": b["b_date"].isoformat() if b["b_date"] else "",
            "invoice_amount": f"{n_amount:.2f}", "amount_received": f"{(amt_rcd + int_amt - c_dis):.2f}",
            "balance": f"{balance:.2f}", "day_over": day_diff,
        })
        total_balance += balance

    return {
        "party_code": party_code, "party_name": _clean(party[0]["cname"]) or "",
        "address_1": _clean(party[0]["cadd1"]) or "", "address_2": _clean(party[0]["cadd2"]) or "",
        "address_3": _clean(party[0]["cadd3"]) or "", "rows": rows, "total_balance": f"{total_balance:.2f}",
    }


class PartyOutstandingLetter2View(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/party_outstanding_letter2.html"

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
def pol2_export(request):
    from io import BytesIO

    from django.conf import settings
    from openpyxl import Workbook
    from openpyxl.styles import Font

    party_code, run_date = _params(request)
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    data = party_outstanding_letter2_rows(party_code, run_date)
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

    header = ["INV NO.", "INV DATE", "INV AMOUNT", "AMOUNT RECEIVED", "BALANCE", "D/OVER"]
    widths = [6, 10, 12, 20, 15, 10]
    ws.append(header)
    header_row = ws.max_row
    for c in ws[header_row]:
        c.font = Font(bold=True)
    for w, col in zip(widths, "ABCDEF"):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["B"].number_format = "dd/mm/yy"

    for r in data["rows"]:
        ws.append([
            r["bill_no"], date.fromisoformat(r["bill_date"]) if r["bill_date"] else None,
            float(r["invoice_amount"]), float(r["amount_received"]), float(r["balance"]), r["day_over"],
        ])
        ws.cell(row=ws.max_row, column=3).number_format = "0.00"
        ws.cell(row=ws.max_row, column=4).number_format = "0.00"
        ws.cell(row=ws.max_row, column=5).number_format = "0.00"

    ws.append(["", "", "", "TOTAL", float(data["total_balance"])])
    ws.append([])
    ws.append([f"For {settings.BRAND['name'].upper()}"])
    ws.append([])
    ws.append(["Authorized Signatory"])
    ws.append(["Interest @21% will be charged after 60 days from the date of Invoice."])

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Party_Outstanding_Letter2_{party_code}_{run_date:%d-%m-%Y}.xlsx"'
    return response

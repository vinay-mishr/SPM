import json
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .services import MoneyReceiptError


def _can_edit(user):
    return settings.LEGACY_WRITES_ENABLED


def _parse(value, default):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


class MoneyReceiptView(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/money_receipt_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["can_edit"] = _can_edit(self.request.user)
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def mr_list(request):
    start = _parse(request.GET.get("start_date"), date.today())
    end = _parse(request.GET.get("end_date"), date.today())
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    return JsonResponse({"rows": services.list_receipts(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def mr_detail(request):
    p_code = request.GET.get("p_code", "")
    chq_no = request.GET.get("chq_no", "")
    slip_dt = request.GET.get("slip_dt", "")
    data = services.get_receipt(p_code, chq_no, slip_dt)
    if not data:
        return JsonResponse({"message": "Money Receipt not found."}, status=404)
    data["history_rows"] = services.history_rows(data["party_code"], exclude=(p_code, chq_no, slip_dt))
    return JsonResponse(data)


@login_required
@require_GET
def mr_parties(request):
    return JsonResponse({"parties": services.search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def mr_party(request):
    code = request.GET.get("code", "")
    data = services.party_detail(code)
    if not data:
        return JsonResponse({"message": "Party not found."}, status=404)
    data["previous_advance"] = str(services.previous_advance(data["code"]))
    data["ledger_balance"] = str(services.ledger_balance(data["code"]))
    data["pending_bills"] = services.pending_bills(data["code"])
    data["history_rows"] = services.history_rows(data["code"])
    return JsonResponse(data)


@login_required
@require_GET
def mr_ledgers(request):
    return JsonResponse({"ledgers": services.search_ledgers(request.GET.get("q", ""))})


@login_required
@require_GET
def mr_next_cash_no(request):
    return JsonResponse({"chq_no": str(services.next_cash_receipt_no())})


@login_required
@require_POST
def mr_save(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change Money Receipts."}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    try:
        result = services.save_receipt(body, username=request.user.get_username())
    except MoneyReceiptError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Money Receipt {result['vou_no']} saved.", **result})


@login_required
@require_POST
def mr_delete(request):
    if not _can_edit(request.user):
        return JsonResponse({"message": "You don't have permission to change Money Receipts."}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    p_code = (body.get("p_code") or "").strip()
    chq_no = (body.get("chq_no") or "").strip()
    slip_dt = (body.get("slip_dt") or "").strip()
    try:
        services.delete_receipt(p_code, chq_no, slip_dt)
    except MoneyReceiptError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": "Money Receipt deleted."})


# --- Party Outstanding (standalone report, separate submenu entry) ----------------------

class PartyOutstandingView(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/party_outstanding.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"run_date": date.today().isoformat()}
        return context


def _outstanding_params(request):
    run_date = _parse(request.GET.get("run_date"), date.today())
    party_code = (request.GET.get("party_code") or "").strip().upper() or None
    return run_date, party_code


@login_required
@require_GET
def party_outstanding_data(request):
    run_date, party_code = _outstanding_params(request)
    return JsonResponse(services.party_outstanding_report(run_date, party_code))


@login_required
@require_GET
def party_outstanding_export(request):
    from io import BytesIO
    from django.conf import settings
    from openpyxl import Workbook
    from openpyxl.styles import Font, Border, Side
    from django.http import HttpResponse

    run_date, party_code = _outstanding_params(request)
    data = services.party_outstanding_report(run_date, party_code)

    thin = Side(style="medium", color="000000")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)

    def bordered_row(ws, values):
        """Appends a row and boxes every one of its 11 columns (A:K), even
        the ones left blank -- matches the bordered grid look of the real
        report's own Excel export, not just the header."""
        ws.append(values)
        r = ws.max_row
        for col in range(1, 12):
            ws.cell(row=r, column=col).border = box

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([settings.BRAND["name"].upper()])
    ws.append([f"PARTY WISE OUTSTANDING AS ON {run_date:%d/%m/%Y}"])
    ws.append([])
    header = ["Bill No.", "Bill Date", "Bill Amt.", "Amt.Received", "Dr.Note Amt.", "Cr.Note Amt.",
              "Balance Amt.", "Below 30 Days", "31 to 60 Days", "61 to 90 Days", "Above 90 Days"]
    bordered_row(ws, header)
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for w, col in zip([10, 12, 13, 13, 13, 13, 13, 14, 14, 14, 14], "ABCDEFGHIJK"):
        ws.column_dimensions[col].width = w
    for g in data["groups"]:
        ws.append([f"{g['party_name']}, {g['city']}, {g['party_code']}, GSTIN:"])
        if float(g["advance"]):
            bordered_row(ws, ["ADVANCE", "", "", "", "", "", -float(g["advance"])])
        for l in g["rows"]:
            row = [l["bill_no"], l["bill_date"], float(l["bill_amount"]), float(l["amount_received"]),
                   float(l["dr_note"]), float(l["cr_note"]), float(l["balance"])]
            slot = {"below_30": 7, "between_31_60": 8, "between_61_90": 9, "above_90": 10}[l["bucket"]]
            row += [None] * (slot - len(row))
            row.append(float(l["balance"]))
            bordered_row(ws, row)
        bordered_row(ws, ["", "", "", "", "", "TOTAL", float(g["total_balance"]), float(g["below_30"]),
                   float(g["between_31_60"]), float(g["between_61_90"]), float(g["above_90"])])
    ws.append([])
    ws.append(["", "", "", "", "S U M M A R Y"])
    ws.append(["", "", "", "", "BELOW 30 DAY", float(data["below_30"])])
    ws.append(["", "", "", "", "31 TO 60 DAYS", float(data["between_31_60"])])
    ws.append(["", "", "", "", "61 TO 90 DAYS", float(data["between_61_90"])])
    ws.append(["", "", "", "", "ABOVE 90 DAYS", float(data["above_90"])])
    ws.append(["", "", "", "", "TOTAL AMOUNT", float(data["total_balance"])])
    ws.append(["", "", "", "", "(-)UNADJUSTED ADVANCE", float(data["advance"])])
    ws.append(["", "", "", "", "TOTAL OUTSTANDING", float(data["net_outstanding"])])

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Party_Wise_Outstanding_{run_date:%d-%m-%Y}.xlsx"'
    return response

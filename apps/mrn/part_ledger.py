"""MRN > Stock Ledger -- per-part ledger, following the old VFP stock ledger rules.

Movements come from imaster:
  P  MRN receipts (mrn_no set, dated m_dat, qty po_qty)            receipt
  R  challan receipts (bill_no, stts R, no job)                     receipt
  I  single issues (bill_no, stts I, no job)                        issue
  A  debit notes (gdb_no set)                                       issue
  S  bill issues (bill_no, stts S, no job)                          issue
  B  job issues (job_no / jo_no / jb_no)                            issue
Opening = part op_stk + movements before the start date.
Credit notes (a sales return -- goods coming back increase stock) come from
the separate g_master table (apps.credit_note.models.GMasterCreditLine,
bill_type='C'), not imaster -- apps.credit_note.services.save()/delete()
adjust Part.current_stock (cur_stk) against this same table, so this is the
one additional movement source needed to make the Stock Ledger agree with it:
  C  credit note lines (bill_type='C')                              receipt
"""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connections
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from apps.parties.models import Party
from apps.parts.models import Part
from apps.credit_note.models import GMasterCreditLine

RECEIPT = {"P", "R", "C"}
ISSUE = {"I", "A", "S", "B"}
_CN_LINE_TYPE = Q(bill_type="C") | Q(bill_type="") | Q(bill_type__isnull=True)


def _clean(value):
    return (value or "").strip()


def _movements():
    cur = connections["legacy"].cursor()
    cur.execute("SELECT i_code, mrn_no, m_dat, po_qty, rate, p_code, bill_no, date, qty, stts, job_no, "
                "gdb_no, jo_no, jb_no FROM imaster")
    out = []
    for (code, mrn_no, m_dat, po_qty, rate, p_code, bill_no, dt, qty, stts, job_no, gdb_no, jo_no, jb_no) in cur.fetchall():
        code = _clean(code)
        if not code:
            continue
        party = _clean(p_code)
        if _clean(mrn_no):
            out.append((code, m_dat, "P", "MRN." + _clean(mrn_no), party, rate, po_qty))
        if _clean(bill_no) and _clean(stts) == "I" and not _clean(job_no):
            out.append((code, dt, "I", "Single.Iss." + _clean(bill_no), party, None, qty))
        if _clean(bill_no) and _clean(stts) == "R" and not _clean(job_no):
            out.append((code, dt, "R", "Chl.No." + _clean(bill_no), party, None, qty))
        if _clean(gdb_no):
            out.append((code, dt, "A", "Debit." + _clean(gdb_no), party, rate, qty))
        if _clean(bill_no) and _clean(stts) == "S" and not _clean(job_no):
            out.append((code, dt, "S", "Bill." + _clean(bill_no), party, rate, qty))
        if _clean(job_no) and not _clean(bill_no) and not _clean(jo_no) and not _clean(jb_no):
            out.append((code, dt, "B", "Job.No." + _clean(job_no), party, None, qty))
        if _clean(jo_no):
            out.append((code, dt, "B", "Iss.Job.No." + _clean(jo_no), party, None, qty))
        if _clean(jb_no):
            out.append((code, dt, "B", "Iss.Job.No." + _clean(jb_no), party, None, qty))

    for code, dt, bill_no, p_code, rate, qty in GMasterCreditLine.objects.filter(_CN_LINE_TYPE).values_list(
        "item_code", "line_date", "bill_no", "party_code", "rate", "qty"
    ):
        code = _clean(code)
        if not code or not qty:
            continue
        out.append((code, dt, "C", "C.Note." + _clean(bill_no), _clean(p_code), rate, qty))
    return out


def part_ledger(start, end, part_code=None):
    """[{code, name, opening, rows:[...], rec_total, iss_total, closing}] for the chosen parts."""
    moves = _movements()
    parts = {p: (d, op) for p, d, op in Part.objects.values_list("part_number", "description_1", "opening_stock")}
    if part_code:
        if part_code not in parts:
            return None
        codes = [part_code]
    else:
        codes = sorted(parts)
    names = dict(Party.objects.values_list("party_code", "name"))
    by_code = {}
    for m in moves:
        by_code.setdefault(m[0], []).append(m)

    result = []
    for code in codes:
        name, op = parts.get(code, ("", None))
        balance = Decimal(op or 0)
        before = [m for m in by_code.get(code, []) if m[1] and m[1] < start]
        for m in before:
            qty = Decimal(m[6] or 0)
            balance += qty if m[2] in RECEIPT else -qty
        opening = balance
        in_range = [m for m in by_code.get(code, []) if m[1] and start <= m[1] <= end]
        if not in_range and opening == 0 and not part_code:
            continue
        rows, rec_total, iss_total = [], Decimal("0"), Decimal("0")
        for m in sorted(in_range, key=lambda x: x[1]):
            qty = Decimal(m[6] or 0)
            rec = qty if m[2] in RECEIPT else Decimal("0")
            iss = qty if m[2] in ISSUE else Decimal("0")
            balance += rec - iss
            rec_total += rec
            iss_total += iss
            rows.append({
                "date": m[1].isoformat(), "ref_no": m[3],
                "party": _clean(names.get(m[4])) or m[4] or "",
                "rate": f"{Decimal(m[5] or 0):.2f}" if m[5] is not None else "",
                "rec": f"{rec:.2f}" if rec else "", "iss": f"{iss:.2f}" if iss else "",
                "bal": f"{balance:.2f}",
            })
        if not rows and opening == 0:
            continue
        result.append({"code": code, "name": _clean(name), "opening": f"{opening:.2f}", "rows": rows,
                       "rec_total": f"{rec_total:.2f}", "iss_total": f"{iss_total:.2f}",
                       "closing": f"{balance:.2f}"})
    return result


def _parse(raw, default):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def _range(request):
    today = date.today()
    return _parse(request.GET.get("start_date"), today), _parse(request.GET.get("end_date"), today)


class PartLedgerView(LoginRequiredMixin, TemplateView):
    template_name = "mrn/part_ledger.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        fy_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
        context["initial_data"] = {"start_date": fy_start.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def part_ledger_data(request):
    start, end = _range(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    part_code = (request.GET.get("part_code") or "").strip().upper() or None
    data = part_ledger(start, end, part_code)
    if data is None:
        return JsonResponse({"message": "Part not found."}, status=404)
    return JsonResponse({"parts": data})


@login_required
@require_GET
def part_ledger_export(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    start, end = _range(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)
    part_code = (request.GET.get("part_code") or "").strip().upper() or None
    data = part_ledger(start, end, part_code)
    if data is None:
        return JsonResponse({"message": "Part not found."}, status=404)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([settings.BRAND["name"].upper()])
    ws.append([f"STOCK LEDGER FROM {start:%d/%m/%Y} TO {end:%d/%m/%Y}"])
    ws.append([])
    ws.append(["REF DATE", "REF NO.", "PARTY", "RATE", "REC.QTY", "ISS.QTY", "BAL.QTY"])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for w, col in zip([12, 20, 32, 10, 10, 10, 10], "ABCDEFG"):
        ws.column_dimensions[col].width = w
    for p in data:
        ws.append([])
        ws.append([f"{p['code']}  {p['name']}", None, None, None, None, None, None])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.append([None, "OPENING", None, None, None, None, float(p["opening"])])
        for r in p["rows"]:
            ws.append([r["date"], r["ref_no"], r["party"], float(r["rate"]) if r["rate"] else None,
                       float(r["rec"]) if r["rec"] else None, float(r["iss"]) if r["iss"] else None, float(r["bal"])])
        ws.append([None, None, "TOTAL", None, float(p["rec_total"]), float(p["iss_total"]), float(p["closing"])])
        ws.cell(row=ws.max_row, column=3).font = Font(bold=True)
    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="Stock_Ledger.xlsx"'
    return response

"""Reports > Sales Reports > Daily Sale (VFP "DAILY REPORT" form, OLE-Excel
export block).

One row per calendar day from Start Date to End Date (inclusive), mixing
four unrelated per-day figures -- preserved exactly, including the
source's own quirks:
  * SALE: ``SUM(bill.n_amount)`` for bills dated that day (every bill,
    not scoped to any ``bill_type`` or division).
  * PURCHASE: ``SUM(mrn_dat.n_amount)`` for MRN rows whose ``mrn_dt`` is
    that day.
  * JOB CARD OPEN: new job cards STARTED that day (``new_job.date``) --
    count and total qty, plus an "open value" priced off ``item.rate``
    for the item code found by truncating the job's own ``i_code`` to its
    first 4 characters (``LEFT(i_code, 4)`` -- the job card's code
    carries a longer composite suffix; only the base item code is looked
    up). The VFP source's own day-TOTAL row for this column
    (``tjobopen=tjobopen``) never actually accumulates anything -- always
    0 -- preserved as written, not "fixed" into a real running total.
  * JOB CARD CLOSE: job cards CLOSED that day (``new_job.cl_date``) --
    count and a quantity that's ``product + product1`` (two separate
    received-quantity columns summed), valued the same truncated-code way
    as JOB CARD OPEN.

The sheet's own header row has ten columns, but the VFP source only ever
writes nine distinct values across them -- "JOB CARD CLOSE (VALUE)"
(column G) and the LAST "JOB CARD CLOSE (VALUE)" (column J, a duplicate
header label) are both written the SAME ``mjobcloseval`` figure; preserved
verbatim, not merged into one column.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connections
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView


def _rows(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _d(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal("0")


def daily_sale_rows(start, end):
    sales = {r["b_date"]: _d(r["total"]) for r in _rows(
        "SELECT b_date, SUM(n_amount) AS total FROM bill WHERE b_date >= %s AND b_date <= %s GROUP BY b_date",
        [start, end],
    )}
    purchases = {r["mrn_dt"]: _d(r["total"]) for r in _rows(
        "SELECT mrn_dt, SUM(n_amount) AS total FROM mrn_dat WHERE mrn_dt >= %s AND mrn_dt <= %s GROUP BY mrn_dt",
        [start, end],
    )}
    opened = _rows(
        "SELECT date, i_code, qty FROM new_job WHERE date >= %s AND date <= %s", [start, end],
    )
    closed = _rows(
        "SELECT cl_date, i_code, product, product1 FROM new_job WHERE cl_date >= %s AND cl_date <= %s",
        [start, end],
    )

    item_codes = {_clean(r["i_code"])[:4] for r in opened + closed if _clean(r["i_code"])}
    rates = {}
    if item_codes:
        for r in _rows(
            "SELECT i_code, rate FROM item WHERE i_code IN (%s)" % ",".join(["%s"] * len(item_codes)),
            list(item_codes),
        ):
            rates[_clean(r["i_code"])] = _d(r["rate"])

    by_day = {}
    for r in opened:
        by_day.setdefault(r["date"], {"open_count": 0, "open_qty": Decimal("0"), "open_val": Decimal("0"),
                                       "close_count": 0, "close_qty": Decimal("0"), "close_val": Decimal("0")})
        day = by_day[r["date"]]
        qty = _d(r["qty"])
        day["open_count"] += 1
        day["open_qty"] += qty
        day["open_val"] += qty * rates.get(_clean(r["i_code"])[:4], Decimal("0"))
    for r in closed:
        by_day.setdefault(r["cl_date"], {"open_count": 0, "open_qty": Decimal("0"), "open_val": Decimal("0"),
                                          "close_count": 0, "close_qty": Decimal("0"), "close_val": Decimal("0")})
        day = by_day[r["cl_date"]]
        qty = _d(r["product"]) + _d(r["product1"])
        day["close_count"] += 1
        day["close_qty"] += qty
        day["close_val"] += qty * rates.get(_clean(r["i_code"])[:4], Decimal("0"))

    rows = []
    total_sale = total_purchase = Decimal("0")
    total_job_close = 0
    d = start
    sno = 1
    while d <= end:
        day = by_day.get(d, {"open_count": 0, "open_qty": Decimal("0"), "open_val": Decimal("0"),
                              "close_count": 0, "close_qty": Decimal("0"), "close_val": Decimal("0")})
        sale = sales.get(d, Decimal("0"))
        purchase = purchases.get(d, Decimal("0"))
        rows.append({
            "sno": sno, "date": d.isoformat(), "sale": f"{sale:.2f}", "purchase": f"{purchase:.2f}",
            "job_open": day["open_count"], "job_open_qty": f"{day['open_qty']:.2f}",
            "job_close_value_1": f"{day['close_val']:.2f}", "job_close": day["close_count"],
            "job_close_qty": f"{day['close_qty']:.2f}", "job_close_value_2": f"{day['close_val']:.2f}",
        })
        total_sale += sale
        total_purchase += purchase
        total_job_close += day["close_count"]
        sno += 1
        d += timedelta(days=1)

    totals = {"sale": f"{total_sale:.2f}", "purchase": f"{total_purchase:.2f}", "job_open": 0,
              "job_close": total_job_close}
    return rows, totals


class DailySaleView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/daily_sale.html"

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
def ds_export(request):
    from io import BytesIO

    from django.conf import settings
    from openpyxl import Workbook
    from openpyxl.styles import Font

    start, end = _params(request)
    if start > end:
        return JsonResponse({"message": "Start Date cannot be later than End Date."}, status=400)

    rows, totals = daily_sale_rows(start, end)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([settings.BRAND["name"].upper()])
    ws.append([settings.BRAND.get("address_line1", "")])
    ws.append([f"DAILY REPORT              PERIOD FROM {start:%d/%m/%Y} TO {end:%d/%m/%Y}"])

    header = ["S.NO", "DATE", "SALE", "PURCHASE", "JOB CARD OPEN", "JOB CARD OPEN (QTY)",
               "JOB CARD CLOSE (VALUE)", "JOB CARD CLOSE", "JOB CARD CLOSE (QTY)", "JOB CARD CLOSE (VALUE)"]
    widths = [8, 12, 12, 15, 15, 15, 15, 15, 15, 15]
    ws.append(header)
    header_row = ws.max_row
    for c in ws[header_row]:
        c.alignment = c.alignment.copy(horizontal="center", vertical="center", wrap_text=True)
        c.font = Font(bold=True)
    for w, col in zip(widths, "ABCDEFGHIJ"):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["B"].number_format = "dd/mm/yyyy"

    for r in rows:
        ws.append([
            r["sno"], date.fromisoformat(r["date"]), float(r["sale"]), float(r["purchase"]),
            r["job_open"], float(r["job_open_qty"]), float(r["job_close_value_1"]), r["job_close"],
            float(r["job_close_qty"]), float(r["job_close_value_2"]),
        ])
        for col in ("C", "D", "F", "G", "I", "J"):
            ws[f"{col}{ws.max_row}"].number_format = "0.00"

    ws.append(["", "Total", float(totals["sale"]), float(totals["purchase"]), totals["job_open"], "", "",
               totals["job_close"]])

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Daily_Sale_{start:%d-%m-%Y}_to_{end:%d-%m-%Y}.xlsx"'
    return response

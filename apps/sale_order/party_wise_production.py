"""Reports > Sales Reports > Party Wise Production (VFP "PARTYWISE ORDER AND
SALE REPORT" form, OLE-Excel export block).

One row per ``order1`` line (apps.sale_order's own Sale Order stock-
reconciliation table -- see apps.gst_invoice.services' own docstring for
why it's addressed with raw SQL rather than an unmanaged model) dated on
or before RUN DATE, grouped under a header row per party (``p_code``) --
the VFP source's own single ``do while p_code=mpcode`` pass over the
table's own ``picode`` index (party then item), so this port groups and
orders the same way: by party, then by the line's own row order.

A party header shows ``cust_mst.ccode + ',' + cname + ',' + cadd3`` exactly
as the VFP source concatenates it (not split into separate columns) --
preserved verbatim, not "fixed" into separate Code/Name/City cells. A line
with no matching ``cust_mst`` row still gets a header (blank code/name/
city), same as the VFP source's own unconditional ``seek``.

ORDER QTY/AMT read straight off ``order1.stock``/``stock * brate`` and
SALE QTY/AMT off ``order1.issue``/``issue * brate`` -- both names the VFP
source itself uses (``stock`` here means "ordered quantity", not a
warehouse stock balance; see apps.purchase_orders.services' own note on
the same table's confusing column name elsewhere in this project). No
``adj <> 'Y'`` filter is applied -- the VFP source's own ``SET FILTER``
here is only the date, unlike e.g. apps.items.month_wise_sale's pending-
order calculation.
"""
from datetime import date
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


def party_wise_production_rows(run_date):
    lines = _rows(
        "SELECT div, p_code, i_code, stock, brate, issue FROM order1 WHERE date <= %s ORDER BY p_code, i_code",
        [run_date],
    )
    p_codes = sorted({_clean(l["p_code"]) or "" for l in lines})
    i_codes = sorted({_clean(l["i_code"]) or "" for l in lines})

    parties = {_clean(r["ccode"]): r for r in _rows(
        "SELECT ccode, cname, cadd3 FROM cust_mst WHERE ccode IN (%s)" % ",".join(["%s"] * len(p_codes)),
        p_codes,
    )} if p_codes else {}
    items = {_clean(r["i_code"]): r for r in _rows(
        "SELECT i_code, i_name FROM item WHERE i_code IN (%s)" % ",".join(["%s"] * len(i_codes)),
        i_codes,
    )} if i_codes else {}

    groups = []
    current = None
    for l in lines:
        p_code = _clean(l["p_code"]) or ""
        if current is None or current["p_code"] != p_code:
            party = parties.get(p_code)
            header = (p_code + "," + _clean(party["cname"]) + "," + _clean(party["cadd3"])) if party \
                else (p_code + ",,")
            current = {"div": _clean(l["div"]) or "", "p_code": p_code, "header": header, "lines": []}
            groups.append(current)
        item = items.get(_clean(l["i_code"]) or "")
        stock = _d(l["stock"])
        issue = _d(l["issue"])
        brate = _d(l["brate"])
        current["lines"].append({
            "item_code": _clean(l["i_code"]) or "", "item_name": _clean(item["i_name"]) if item else "",
            "order_qty": f"{stock:.2f}", "order_amt": f"{(stock * brate):.2f}",
            "sale_qty": f"{issue:.2f}", "sale_amt": f"{(issue * brate):.2f}",
        })
    return groups


class PartyWiseProductionView(LoginRequiredMixin, TemplateView):
    template_name = "sale_order/party_wise_production.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"run_date": date.today().isoformat()}
        return context


def _params(request):
    try:
        return date.fromisoformat(request.GET.get("run_date"))
    except (TypeError, ValueError):
        return date.today()


@login_required
@require_GET
def pwp_export(request):
    from io import BytesIO

    from django.conf import settings
    from openpyxl import Workbook
    from openpyxl.styles import Font

    run_date = _params(request)
    groups = party_wise_production_rows(run_date)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([settings.BRAND["name"].upper()])
    ws.append([settings.BRAND.get("address_line1", "")])
    ws.append([f"PARTYWISE ORDER AND SALE REPORT AS ON {run_date:%d/%m/%Y}"])

    header = ["DIV", "CODE", "ITEM NAME", "ORDER QTY.", "ORDER AMT.", "SALE QTY.", "SALE.AMT."]
    widths = [50, 10, 30, 12, 12, 12, 10]
    ws.append(header)
    header_row = ws.max_row
    for c in ws[header_row]:
        c.font = Font(bold=True)
    for w, col in zip(widths, "ABCDEFG"):
        ws.column_dimensions[col].width = w

    for g in groups:
        ws.append([g["header"]])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        for l in g["lines"]:
            ws.append([
                "", l["item_code"], l["item_name"], float(l["order_qty"]), float(l["order_amt"]),
                float(l["sale_qty"]), float(l["sale_amt"]),
            ])

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Party_Wise_Production_{run_date:%d-%m-%Y}.xlsx"'
    return response

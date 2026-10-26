"""Reports > Sales Reports > Party Wise Item List (VFP "PARTY WISE ITEM
LIST" form, OLE-Excel export block).

One row per ``part-mst`` row (apps.parts.models.Part's own table; note the
real table's hyphen) that names the selected, required party as ANY of its
four supplier slots (``party1``..``party4``) -- each slot carries its own
rate (``rate1``..``rate4``), and the row's RATE column is whichever slot
matched, exactly the VFP source's own ``do case`` (a part naming the same
party in two slots -- not expected in real data, not guarded against --
would print twice, once per matching slot, same as the VFP source's own
unconditional ``case`` block).

The header also shows the party's own ``cust_mst.grade`` next to its name
-- read verbatim off ``cust_mst.grade`` (via the "cust" alias the VFP
source's own party-picker handler opens ``cust_mst`` under elsewhere), not
derived or guessed.
"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connections
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

PARTY_SLOTS = [("party1", "rate1"), ("party2", "rate2"), ("party3", "rate3"), ("party4", "rate4")]


def _rows(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _d(value):
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def party_wise_item_list(party_code):
    party = _rows("SELECT ccode, cname, grade FROM cust_mst WHERE ccode = %s", [party_code])
    if not party:
        return None

    parts = _rows(
        "SELECT icod, ides, party1, rate1, party2, rate2, party3, rate3, party4, rate4 "
        "FROM [part-mst] ORDER BY icod"
    )

    rows = []
    for p in parts:
        for party_field, rate_field in PARTY_SLOTS:
            if _clean(p[party_field]) == party_code:
                rows.append({
                    "item_code": _clean(p["icod"]) or "", "item_name": _clean(p["ides"]) or "",
                    "rate": f"{_d(p[rate_field]):.2f}",
                })

    return {
        "party_code": party_code, "party_name": _clean(party[0]["cname"]) or "",
        "grade": _clean(party[0]["grade"]) or "", "rows": rows,
    }


class PartyWiseItemListView(LoginRequiredMixin, TemplateView):
    template_name = "parts/party_wise_item_list.html"


@login_required
@require_GET
def pwil_export(request):
    from io import BytesIO

    from django.conf import settings
    from openpyxl import Workbook
    from openpyxl.styles import Font

    party_code = (request.GET.get("party_code") or "").strip().upper()
    if not party_code:
        return JsonResponse({"message": "Select a party first."}, status=400)
    data = party_wise_item_list(party_code)
    if data is None:
        return JsonResponse({"message": "Party not found."}, status=404)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([settings.BRAND["name"].upper()])
    ws.append(["PARTY WISE ITEM LIST"])
    ws.append([f"{data['party_name']} GRADE {data['grade']}"])
    ws.append([])

    header = ["CODE", "ITEM NAME", "RATE"]
    widths = [10, 30, 10]
    ws.append(header)
    header_row = ws.max_row
    for c in ws[header_row]:
        c.font = Font(bold=True)
    for w, col in zip(widths, "ABC"):
        ws.column_dimensions[col].width = w

    for r in data["rows"]:
        ws.append([r["item_code"], r["item_name"], float(r["rate"])])
        ws.cell(row=ws.max_row, column=3).number_format = "0.00"

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Party_Wise_Item_List_{party_code}.xlsx"'
    return response

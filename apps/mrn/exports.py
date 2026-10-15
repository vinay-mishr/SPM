"""Pending MRN report — Excel export (openpyxl). Mirrors the old VFP report's
column layout (MRN DATE, MRN NO., PARTY NAME, PARTY CITY)."""
from io import BytesIO


def _date(iso):
    if not iso:
        return None
    from datetime import date
    y, m, d = iso.split("-")
    return date(int(y), int(m), int(d))


PENDING_MRN_COLUMNS = [
    ("MRN DATE", 12, "dd/mm/yyyy"),
    ("MRN NO.", 10, "@"),
    ("PARTY NAME", 32, "@"),
    ("PARTY CITY", 22, "@"),
]


def build_pending_mrn_workbook(rows, company_name, start_date, end_date):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Border, Font, Side

    font_name = "Arial Narrow"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()
    ws = wb.active
    ws.title = "Pending MRN"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font_name, size=10, bold=True)
    ws.cell(
        row=2, column=1,
        value=f"PENDING MRN REPORT FROM DATE {start_date.strftime('%d/%m/%Y')} TO {end_date.strftime('%d/%m/%Y')}",
    ).font = Font(name=font_name, size=10, bold=True)

    header_row = 3
    for col, (heading, width, _fmt) in enumerate(PENDING_MRN_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font_name, size=10, bold=True)
        cell.alignment = cell.alignment.copy(horizontal="center", vertical="center")
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for line in rows:
        values = [_date(line["mrn_date"]), line["mrn_no"], line["party_name"], line["party_city"]]
        for col, (value, (_heading, _width, fmt)) in enumerate(zip(values, PENDING_MRN_COLUMNS), start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value) if value not in ("", None) else None)
            cell.font = Font(name=font_name, size=10)
            cell.number_format = fmt
        row += 1

    for r in range(header_row, row):
        for c in range(1, len(PENDING_MRN_COLUMNS) + 1):
            ws.cell(row=r, column=c).border = border

    ws.freeze_panes = f"A{header_row + 1}"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_current_stock_workbook(rows, company_name, start_date, end_date):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Border, Font, Side

    font = "Arial"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook()
    ws = wb.active
    ws.title = "Current Stock"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font, size=12, bold=True)
    ws.cell(row=3, column=1, value=f"CURRENT STOCK From {start_date.strftime('%d/%m/%Y')} TO {end_date.strftime('%d/%m/%Y')}").font = Font(name=font, size=10, bold=True)

    headers = [("Sno", 6, "@"), ("ITEM CODE", 12, "@"), ("ITEM DESCRIPTION", 40, "@"), ("STOCK", 12, "0.00")]
    header_row = 4
    for col, (heading, width, _f) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font, size=8, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for r in rows:
        values = [r["sno"], r["item_code"][:10], r["item_name"][:50], float(r["stock"])]
        for col, (value, (_h, _w, fmt)) in enumerate(zip(values, headers), start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value))
            cell.font = Font(name=font, size=8)
            cell.number_format = fmt
            cell.border = border
        row += 1

    ws.freeze_panes = f"A{header_row + 1}"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


STOCK_STATEMENT_COLUMNS = [
    ("SNO", 5, "0"), ("CODE", 12, "@"), ("ITEM DESCRIPTION", 32, "@"), ("UNIT", 6, "@"),
    ("GRADE", 6, "@"), ("ROL", 9, "0.00"), ("MATERIAL", 14, "@"), ("WT./100", 10, "0.000"),
    ("OP. BAL.", 11, "0.000"), ("REC.QTY.", 11, "0.000"), ("ISSUED QTY.", 11, "0.000"),
    ("INV.RATE", 10, "0.00"), ("BAL. QTY.", 11, "0.000"), ("BAL.VALUE", 13, "#,##0.00"), ("WEIGHT", 11, "0.000"),
]


def build_stock_statement_workbook(rows, company_name, start_date, end_date):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Border, Font, Side

    font = "Arial"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock Statement"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font, size=11, bold=True)
    ws.cell(row=3, column=1, value=f"STOCK STATEMENT FROM {start_date.strftime('%d/%m/%Y')} TO {end_date.strftime('%d/%m/%Y')}").font = Font(name=font, size=10, bold=True)

    header_row = 4
    for col, (heading, width, _f) in enumerate(STOCK_STATEMENT_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font, size=8, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width

    NUMERIC_KEYS = {"rol", "wt100", "opening", "received", "issued", "rate", "balance", "balance_value", "weight"}
    keys = ["sno", "item_code", "item_name", "unit", "grade", "rol", "material", "wt100",
            "opening", "received", "issued", "rate", "balance", "balance_value", "weight"]
    row = header_row + 1
    total = 0.0
    for r in rows:
        for col, (key, (_h, _w, fmt)) in enumerate(zip(keys, STOCK_STATEMENT_COLUMNS), start=1):
            raw = r[key]
            if key == "sno":
                value = int(raw)
            elif key in NUMERIC_KEYS:
                value = float(raw)
            else:
                value = raw
            cell = ws.cell(row=row, column=col, value=sanitize(value) if value not in ("", None) else None)
            cell.font = Font(name=font, size=8)
            cell.number_format = fmt
            cell.border = border
        total += float(r["balance_value"])
        row += 1

    ws.cell(row=row, column=14, value="TOTAL").font = Font(name=font, size=8, bold=True)
    tot = ws.cell(row=row, column=15, value=total)
    tot.font = Font(name=font, size=8, bold=True)
    tot.number_format = "#,##0.00"
    ws.freeze_panes = f"A{header_row + 1}"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_stock_ledger_workbook(rows, company_name, start_date, end_date):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Border, Font, Side

    font = "Arial"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock Ledger"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font, size=11, bold=True)
    ws.cell(row=2, column=1, value="RAW MATERIAL STOCK STATEMENT (VALUE-WISE)").font = Font(name=font, size=10, bold=True)
    ws.cell(row=3, column=1, value=f"DATE FROM {start_date.strftime('%d/%m/%Y')} TO {end_date.strftime('%d/%m/%Y')}").font = Font(name=font, size=10, bold=True)

    headers = [("CODE", 12, "@"), ("PRODUCT NAME", 34, "@"), ("CUR.STK.", 12, "0.000"), ("VALUE", 14, "#,##0.00"), ("WEIGHT", 12, "0.000")]
    header_row = 5
    for col, (heading, width, _f) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font, size=8, bold=True)
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    total = 0.0
    for r in rows:
        values = [r["item_code"], r["item_name"], float(r["balance"]), float(r["value"]), float(r["weight"])]
        for col, (value, (_h, _w, fmt)) in enumerate(zip(values, headers), start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value))
            cell.font = Font(name=font, size=8)
            cell.number_format = fmt
            cell.border = border
        total += float(r["value"])
        row += 1

    ws.cell(row=row, column=3, value="TOTAL").font = Font(name=font, size=8, bold=True)
    tot = ws.cell(row=row, column=4, value=total)
    tot.font = Font(name=font, size=8, bold=True)
    tot.number_format = "#,##0.00"
    ws.freeze_panes = f"A{header_row + 1}"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_item_monthwise_sale_workbook(rows, company_name, fy_start):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Border, Font, Side

    months = ["April", "May", "June", "July", "August", "September", "October", "November", "December",
              "January", "February", "March"]
    font = "Arial"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook()
    ws = wb.active
    ws.title = "Item-wise Month-wise Sale"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font, size=14, bold=True)
    ws.cell(row=2, column=1, value="ITEM-WISE/MONTHWISE SALE REPORT (QTY WISE)").font = Font(name=font, size=11, bold=True)
    ws.cell(row=3, column=1, value=f"FINANCIAL YEAR FROM {fy_start.strftime('%d/%m/%Y')}").font = Font(name=font, size=9, bold=True)

    headers = [("Item Name", 30), ("UNIT", 6), ("RE.ORD QTY", 11)] + [(m, 10) for m in months] + [("Total", 11), ("Average", 11)]
    header_row = 5
    for col, (heading, width) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font, size=9, bold=True)
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for r in rows:
        values = [r["item_name"], r["unit"], float(r["rop"])] + [float(m) for m in r["months"]] + [float(r["total"]), float(r["average"])]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value) if value not in ("", None) else None)
            cell.font = Font(name=font, size=9)
            cell.border = border
            if col > 2:
                cell.number_format = "0.00"
        row += 1

    ws.freeze_panes = f"B{header_row + 1}"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_critical_shortage_workbook(rows, company_name, start_date, end_date, last_days, cur_days):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Border, Font, Side

    font = "Arial"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook()
    ws = wb.active
    ws.title = "Critical Shortage"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font, size=12, bold=True)
    ws.cell(row=2, column=1, value=f"CRITICAL SHORTAGE FROM {start_date.strftime('%d/%m/%Y')} TO {end_date.strftime('%d/%m/%Y')}").font = Font(name=font, size=10, bold=True)

    headers = [("Sno", 6), ("Code", 12), ("Item Description", 36), ("Unit", 6), ("Balance Qty", 12),
               ("Balance Value", 13), (f"Cur.Yr {cur_days} Days Avg. Consumption", 16),
               (f"Last.Yr {last_days} Days Avg. Consumption", 16), ("Planning Reqd", 12),
               ("Shortage", 12), ("Excess", 12), ("Supplier 1", 22), ("Supplier 2", 22), ("Supplier 3", 22), ("Supplier 4", 22)]
    header_row = 4
    for col, (heading, width) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font, size=8, bold=True)
        cell.border = border
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for r in rows:
        values = [r["sno"], r["item_code"][:10], r["item_name"][:50], r["unit"], float(r["balance"]),
                  float(r["value"]), float(r["cur_use"]), float(r["last_use"]), float(r["planning"]),
                  float(r["shortage"]), float(r["excess"])] + (r["suppliers"] + ["", "", "", ""])[:4]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value) if value not in ("", None) else None)
            cell.font = Font(name=font, size=8)
            cell.border = border
            if 5 <= col <= 11:
                cell.number_format = "#,##0.000" if col != 6 else "#,##0.00"
        row += 1

    ws.freeze_panes = f"A{header_row + 1}"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_crisis_shortage_workbook(rows, company_name, as_on, days, category):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Border, Font, Side

    titles = {"all": "Critical RM Status Report (Excepting Sub Assembly & Workshop items)",
              "routine": "Critical Regular RM Status Report (Excepting Sub Assembly & Workshop items)",
              "subassembly": "Critical Regular RM Status Report (Only Sub Assembly Items)",
              "workshop": "Critical Regular RM Status Report (Only Work Shop Items)"}
    font = "Arial"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook()
    ws = wb.active
    ws.title = "Crisis Shortage"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font, size=12, bold=True)
    ws.cell(row=2, column=1, value=f"{titles.get(category, titles['all'])} as on {as_on.strftime('%d/%m/%Y')} based upon {days} days consumption").font = Font(name=font, size=9, bold=True)

    headers = [("Sno", 6), ("Code", 12), ("Item Description", 34), ("Unit", 6),
               (f"Cur.Yr {days} Days Avg. Consumption", 14), (f"Last.Yr {days} Days Avg. Consumption", 14),
               ("Closing Balance", 12), (f"Shortage as per {days} days Consumption", 16),
               ("Vendor Name", 28), ("PO No", 10), ("Order Pending Qty", 12), ("Desired Despatch Date", 14)]
    header_row = 4
    for col, (heading, width) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font, size=8, bold=True)
        cell.border = border
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for r in rows:
        values = [r["sno"], r["item_code"][:10], r["item_name"][:50], r["unit"], float(r["cur_avg"]),
                  float(r["last_avg"]), float(r["balance"]), float(r["shortage"]), r["vendor"],
                  r["po_no"], float(r["pending"]) if r["pending"] else None, r["despatch"]]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value) if value not in ("", None) else None)
            cell.font = Font(name=font, size=8)
            cell.border = border
            if 5 <= col <= 8 or col == 11:
                cell.number_format = "#,##0.000"
        row += 1

    ws.freeze_panes = f"A{header_row + 1}"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

"""Consumption Master — Excel export (openpyxl). Mirrors the old VFP screen's Excel
button (Excel.Application automation) and print (ITEMLIST.PRN) layout: company name,
"Consumption Master for X", "Item Code : Y", then the 9-column component table with a
bold Total row."""
from io import BytesIO

COLUMNS = [
    ("Sno", 5, "0"),
    ("Code", 12, "@"),
    ("Item Description", 30, "@"),
    ("Qty", 9, "0.000"),
    ("Material", 12, "@"),
    ("Wt/100", 9, "0.000"),
    ("Gauge", 10, "@"),
    ("Drawing No", 12, "@"),
    ("Value(in Rs)", 12, "0.00"),
]


def build_consumption_master_workbook(data, company_name):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Border, Font, Side

    font_name = "Arial Narrow"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()
    ws = wb.active
    ws.title = "Consumption Master"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font_name, size=16, bold=True)
    ws.cell(row=3, column=1, value=f"Consumption Master for {data['item_name']}").font = Font(name=font_name, size=12)
    ws.cell(row=4, column=1, value=f"Item Code : {data['item_code']}").font = Font(name=font_name, size=12)

    header_row = 5
    for col, (heading, width, _fmt) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font_name, size=10, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for line in data["lines"]:
        values = [
            line["sno"], line["code"], line["item_description"], line["quantity"],
            line["material"], line["weight_by_100"], line["gauge"], line["drawing_no"], line["value"],
        ]
        for col, (value, (_heading, _width, fmt)) in enumerate(zip(values, COLUMNS), start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value))
            cell.font = Font(name=font_name, size=10)
            if fmt != "@":
                cell.number_format = fmt
                try:
                    ws.cell(row=row, column=col, value=float(value))
                except (TypeError, ValueError):
                    pass
        row += 1

    ws.cell(row=row, column=3, value="Total").font = Font(name=font_name, size=10, bold=True)
    total_cell = ws.cell(row=row, column=9, value=float(data["total"]))
    total_cell.font = Font(name=font_name, size=10, bold=True)
    total_cell.number_format = "0.00"

    for r in range(header_row, row + 1):
        for c in range(1, len(COLUMNS) + 1):
            ws.cell(row=r, column=c).border = border

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


NO_VALUE_COLUMNS = [
    ("Sno", 5, "0"),
    ("Code", 12, "@"),
    ("Item Description", 30, "@"),
    ("Qty", 8, "0.000"),
    ("Unit", 8, "@"),
    ("Material", 12, "@"),
    ("Wt/100", 10, "0.000"),
    ("Gauge", 12, "@"),
    ("Drawing No", 15, "@"),
]


def build_bom_without_value_workbook(data, company_name):
    """Same layout as build_consumption_master_workbook, minus the Value(in Rs) column
    and the Total row -- old VFP screen's "Without Value" Excel button."""
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Border, Font, Side

    font_name = "Arial Narrow"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()
    ws = wb.active
    ws.title = "BOM Without Value"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font_name, size=16, bold=True)
    ws.cell(row=3, column=1, value=f"Consumption Master for {data['item_name']}").font = Font(name=font_name, size=12)
    ws.cell(row=4, column=1, value=f"Item Code : {data['item_code']}").font = Font(name=font_name, size=12)

    header_row = 5
    for col, (heading, width, _fmt) in enumerate(NO_VALUE_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font_name, size=10, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for line in data["lines"]:
        values = [
            line["sno"], line["code"], line["item_description"], line["quantity"], line["unit"],
            line["material"], line["weight_by_100"], line["gauge"], line["drawing_no"],
        ]
        for col, (value, (_heading, _width, fmt)) in enumerate(zip(values, NO_VALUE_COLUMNS), start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value))
            cell.font = Font(name=font_name, size=10)
            if fmt != "@":
                cell.number_format = fmt
                try:
                    ws.cell(row=row, column=col, value=float(value))
                except (TypeError, ValueError):
                    pass
        row += 1

    ws.cell(row=row, column=3, value="Total").font = Font(name=font_name, size=10, bold=True)

    for r in range(header_row, row + 1):
        for c in range(1, len(NO_VALUE_COLUMNS) + 1):
            ws.cell(row=r, column=c).border = border

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


VALUE_WISE_COLUMNS = [
    ("Sno", 5, "0"),
    ("Code", 12, "@"),
    ("Item Description", 28, "@"),
    ("Hsn code", 10, "@"),
    ("Qty", 8, "0.000"),
    ("Unit", 8, "@"),
    ("Material", 12, "@"),
    ("P.RATE", 10, "0.000"),
    ("S.RATE", 10, "0.00"),
    ("Drawing No", 12, "@"),
    ("Value(in Rs)", 12, "0.00"),
]


def build_sa_value_wise_workbook(data, company_name):
    """Bill of Material Master Value-Wise (Sub Assembly) -- old VFP screen's Excel
    automation macro (sele conms), reference ITEMLIST2.PRN."""
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Border, Font, Side

    font_name = "Arial Narrow"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()
    ws = wb.active
    ws.title = "Value Wise"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font_name, size=16, bold=True)
    ws.cell(row=3, column=1, value=f"Consumption Master for {data['item_name']}").font = Font(name=font_name, size=12)
    ws.cell(row=4, column=1, value=f"Item Code : {data['item_code']}").font = Font(name=font_name, size=12)

    header_row = 5
    for col, (heading, width, _fmt) in enumerate(VALUE_WISE_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font_name, size=10, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for line in data["lines"]:
        values = [
            line["sno"], line["code"], line["item_description"], line["hsn_code"], line["quantity"],
            line["unit"], line["material"], line["purchase_rate"], line["sale_rate"], line["drawing_no"],
            line["value"],
        ]
        for col, (value, (_heading, _width, fmt)) in enumerate(zip(values, VALUE_WISE_COLUMNS), start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value))
            cell.font = Font(name=font_name, size=10)
            if fmt != "@":
                cell.number_format = fmt
                try:
                    ws.cell(row=row, column=col, value=float(value))
                except (TypeError, ValueError):
                    pass
        row += 1

    ws.cell(row=row, column=10, value="Total").font = Font(name=font_name, size=10, bold=True)
    total_cell = ws.cell(row=row, column=11, value=float(data["total"]))
    total_cell.font = Font(name=font_name, size=10, bold=True)
    total_cell.number_format = "0.00"

    for r in range(header_row, row + 1):
        for c in range(1, len(VALUE_WISE_COLUMNS) + 1):
            ws.cell(row=r, column=c).border = border

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


SUPPLIERS_COLUMNS = [
    ("Sno", 5, "0"),
    ("Code", 12, "@"),
    ("Item Description", 26, "@"),
    ("Qty", 8, "0.000"),
    ("Material", 12, "@"),
    ("Supplier-1", 30, "@"),
    ("Supplier-2", 30, "@"),
    ("Supplier-3", 30, "@"),
    ("Supplier-4", 30, "@"),
]


def build_sa_suppliers_workbook(data, company_name):
    """Bill of Material Master Suppliers (Sub Assembly, no value) -- old VFP screen's
    Excel automation macro (sele conms), reference ITEMLIST3.PRN."""
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Border, Font, Side

    font_name = "Arial Narrow"
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()
    ws = wb.active
    ws.title = "Suppliers"

    def sanitize(value):
        return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value

    ws.cell(row=1, column=1, value=company_name).font = Font(name=font_name, size=16, bold=True)
    ws.cell(row=3, column=1, value=f"Consumption Master for {data['item_name']}").font = Font(name=font_name, size=12)
    ws.cell(row=4, column=1, value=f"Item Code : {data['item_code']}").font = Font(name=font_name, size=12)
    ws.cell(row=5, column=1, value=f"Unit : {data['unit']}").font = Font(name=font_name, size=12)

    header_row = 6
    for col, (heading, width, _fmt) in enumerate(SUPPLIERS_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=col, value=heading)
        cell.font = Font(name=font_name, size=10, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width

    row = header_row + 1
    for line in data["lines"]:
        values = [
            line["sno"], line["code"], line["item_description"], line["quantity"], line["material"],
            line["supplier_1"], line["supplier_2"], line["supplier_3"], line["supplier_4"],
        ]
        for col, (value, (_heading, _width, fmt)) in enumerate(zip(values, SUPPLIERS_COLUMNS), start=1):
            cell = ws.cell(row=row, column=col, value=sanitize(value))
            cell.font = Font(name=font_name, size=10)
            if fmt != "@":
                cell.number_format = fmt
                try:
                    ws.cell(row=row, column=col, value=float(value))
                except (TypeError, ValueError):
                    pass
        row += 1

    for r in range(header_row, row):
        for c in range(1, len(SUPPLIERS_COLUMNS) + 1):
            ws.cell(row=r, column=c).border = border

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

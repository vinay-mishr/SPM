"""
Debtors / Creditors list as Excel — the old VFP "DEBTOR'S PRINTING" and
"CREDITOR'S PRINTING" (Excel OLE) rebuilt with openpyxl.

Read-only: parties come from the old software's cust_mst table on the
"legacy" database, filtered on the ledger group code (S001 / S002) and
sorted by name, exactly like ``SELECT cust_mst / SET ORDER TO cname /
SCAN FOR CODE = PSDCODE``.
"""
from io import BytesIO

from django.conf import settings
from django.db import connections
from openpyxl import Workbook
from openpyxl.styles import Border, Font, Side

FONT_NAME = "Arial Narrow"
THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# kind -> (settings key for the ledger group code, column-5 heading, column widths A..J)
LAYOUTS = {
    "debtors": ("PARTY_DEBTOR_CODE", "PHONE NO./MOBILE/EMAIL", [3, 5, 5, 30, 35, 8, 16, 30]),
    "creditors": ("PARTY_CREDITOR_CODE", "PHONE NO./MOBILE", [3, 5, 5, 35, 35, 5, 16, 30]),
}
COLUMNS = ["code", "ccode", "cname", "cphno", "mobile", "cr_days", "pdc", "rpermit",
           "gst_no", "gsname", "stname", "cadd1", "cadd2", "cadd3", "cbadd3"]


class LegacyDatabaseMissing(Exception):
    """The SP_MACHINE (legacy) database connection isn't configured."""


def fetch_parties(kind):
    """Read the parties of one ledger group from cust_mst, sorted by name (read-only)."""
    if "legacy" not in settings.DATABASES:
        raise LegacyDatabaseMissing("The SP_MACHINE database is not connected.")
    group_code = getattr(settings, LAYOUTS[kind][0])
    sql = (
        "SELECT " + ", ".join(f"[{c}]" for c in COLUMNS)
        + " FROM [cust_mst] WHERE [code] = %s ORDER BY [cname]"
    )
    with connections["legacy"].cursor() as cursor:
        cursor.execute(sql, [group_code])
        return [dict(zip(COLUMNS, row)) for row in cursor.fetchall()]


def _text(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def build_workbook(kind, parties, company_name):
    """Build the list in the old layout; returns the .xlsx file as bytes."""
    _, phone_heading, widths = LAYOUTS[kind]
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    def put(row, col, value, bold=False, size=10):
        cell = ws.cell(row=row, column=col, value=value)
        cell.font = Font(name=FONT_NAME, size=size, bold=bold)
        return cell

    put(1, 1, company_name, bold=True, size=12)
    put(2, 1, "CUSTOMER  LIST", bold=True, size=12)

    header_row = 4
    headings = ["SNO", "CODE", "CODE", "PARTY NAME /ADDRESS", phone_heading,
                "CR.DAYS", "GSTIN.", "GST STATE"]
    for col, (heading, width) in enumerate(zip(headings, widths), start=1):
        put(header_row, col, heading, bold=True)
        ws.column_dimensions[chr(64 + col)].width = width

    row = header_row + 1
    for sno, p in enumerate(parties, start=1):
        phone = " ".join(v for v in (_text(p["cphno"]), _text(p["mobile"])) if v)
        state = "-".join(v for v in (_text(p["gsname"]), _text(p["stname"])) if v)
        cr_days = p["cr_days"]
        values = [sno, _text(p["code"]), _text(p["ccode"]), _text(p["cname"]), phone,
                  int(cr_days) if cr_days is not None else None, _text(p["gst_no"]), state]
        for col, value in enumerate(values, start=1):
            cell = put(row, col, value)
            if col == 1:
                cell.number_format = "0"
            if col == 7:
                cell.number_format = "@"  # GSTIN kept as text
        row += 1

        # Address lines under the name: CADD1 (+ CBADD3 alongside), then CADD2 / CADD3 if present.
        put(row, 4, _text(p["cadd1"]))
        put(row, 5, _text(p["cbadd3"]))
        row += 1
        for field in ("cadd2", "cadd3"):
            if _text(p[field]):
                put(row, 4, _text(p[field]))
                row += 1

    # Borders from the heading row to the last row, columns A..H.
    for r in range(header_row, row + 1):
        for c in range(1, 9):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDER
            if cell.font is None or cell.font.name != FONT_NAME:
                cell.font = Font(name=FONT_NAME, size=10)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

"""Accounts > Data Entry > Cash Entry (VFP "CASH ENTRY" form, ttype='CV').

A journal voucher against Cash: each line is posted to ``trans`` (the same
ledger-posting table every sale/receipt/payment module in this project
already writes to -- see e.g. apps.money_receipt.services's own docstring
for its confirmed column list, reused here unchanged) against either a GL
ledger (``gled_mst``) or a customer/vendor sub-ledger (``cust_mst``), and
if none of those lines was posted directly against the Sundry Debtor/
Creditor GROUP code itself (``settings.PARTY_DEBTOR_CODE``/
``PARTY_CREDITOR_CODE`` -- the VFP source's own ``psdcode``/``psccode``,
an edge case for a group-level entry), the screen auto-balances the
voucher with one more ``trans`` line against Cash (``CASH_LEDGER_CODE``,
the same "C001" apps.money_receipt.services already uses) for whatever's
left over between the lines' own total debit and credit -- so the user
only has to key in the "other side" of a cash transaction, never Cash
itself. Voucher numbering reuses the ``vno`` table's ``cvvno`` counter,
the same counter/table apps.money_receipt.services._next_vno already uses
for CASH-mode receipts (this form's own ``ttype`` is hardcoded ``'CV'``,
matching the VFP source's own ``.ttype='CV'``).

A listing row is "this screen's own" line -- as opposed to a trans row any
other module posted -- when every one of these columns is blank: rec_no,
nar, bill_no, pur_no, ent_no, dn_no, stn_no, cn_f, cn_no (the VFP source's
own filter; those are the fields other modules stamp onto their own trans
rows to claim them, e.g. apps.money_receipt uses ``nar``). The auto Cash
leg itself (``tcode = CASH_LEDGER_CODE``) is excluded from both the list
and the edit grid, same as the VFP source's own ``tcode#pcashcode``.

Deliberately not ported (flagged, not guessed):
  * Narration-master autocomplete (``narr_mas`` lookup on the Narration
    field) -- narration is a plain text field here instead.
  * ``group1`` (ledger groups) -- opened by the VFP source but never
    actually read in any of the pasted event handlers for this screen.
"""
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connections, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

TTYPE = "CV"
CASH_LEDGER_CODE = "C001"
PARTY_DEBTOR_CODE = getattr(settings, "PARTY_DEBTOR_CODE", "S001")
PARTY_CREDITOR_CODE = getattr(settings, "PARTY_CREDITOR_CODE", "S002")
Q2 = Decimal("0.01")

OWN_ROW_FILTER = (
    "(rec_no IS NULL OR rec_no = '') AND (nar IS NULL OR nar = '') AND (bill_no IS NULL OR bill_no = '') "
    "AND (pur_no IS NULL OR pur_no = '') AND (ent_no IS NULL OR ent_no = '') AND (dn_no IS NULL OR dn_no = '') "
    "AND (stn_no IS NULL OR stn_no = '') AND (cn_f IS NULL OR cn_f = '') AND (cn_no IS NULL OR cn_no = '')"
)
# Marks the screen's own auto-inserted Cash-balancing leg (see save_voucher) --
# distinct from a line the user deliberately posted against CASH_LEDGER_CODE,
# which a tcode-only filter can't tell apart from the auto leg (both would be
# 'C001'). Blank nar is also what OWN_ROW_FILTER already requires, so tagging
# the auto leg here is what makes it disappear from the list/edit grid.
AUTO_CASH_NAR = "CASH-AUTO"


class CashEntryError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _rows(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exec(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _d(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal("0")


def _date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def search_ledgers(q):
    q = (q or "").strip().upper()
    if q:
        rows = _rows(
            "SELECT gcode, gdesc, gyob FROM gled_mst WHERE UPPER(gcode) LIKE %s OR UPPER(gdesc) LIKE %s ORDER BY gdesc",
            [f"%{q}%", f"%{q}%"],
        )
    else:
        rows = _rows("SELECT gcode, gdesc, gyob FROM gled_mst ORDER BY gdesc")
    return [{"code": _clean(r["gcode"]), "name": _clean(r["gdesc"]) or "", "opening": f"{_d(r['gyob']):.2f}"}
            for r in rows[:20]]


def search_parties(q):
    q = (q or "").strip().upper()
    if q:
        rows = _rows(
            "SELECT ccode, cname, cadd3, cyob FROM cust_mst WHERE UPPER(cname) LIKE %s ORDER BY cname",
            [f"%{q}%"],
        )
    else:
        rows = _rows("SELECT ccode, cname, cadd3, cyob FROM cust_mst ORDER BY cname")
    return [{"code": _clean(r["ccode"]), "name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or "",
             "opening": f"{_d(r['cyob']):.2f}"} for r in rows[:20]]


def ledger_balance(code):
    rows = _rows("SELECT gyob FROM gled_mst WHERE gcode = %s", [code])
    opening = _d(rows[0]["gyob"]) if rows else Decimal("0")
    dc = _rows("SELECT tdbcr, SUM(tamt) AS total FROM trans WHERE tcode = %s GROUP BY tdbcr", [code])
    debit = credit = Decimal("0")
    for r in dc:
        if _clean(r["tdbcr"]) == "D":
            debit = _d(r["total"])
        elif _clean(r["tdbcr"]) == "C":
            credit = _d(r["total"])
    return opening + debit - credit


def party_balance(code):
    rows = _rows("SELECT cyob FROM cust_mst WHERE ccode = %s", [code])
    opening = _d(rows[0]["cyob"]) if rows else Decimal("0")
    dc = _rows("SELECT tdbcr, SUM(tamt) AS total FROM trans WHERE tccode = %s GROUP BY tdbcr", [code])
    debit = credit = Decimal("0")
    for r in dc:
        if _clean(r["tdbcr"]) == "D":
            debit = _d(r["total"])
        elif _clean(r["tdbcr"]) == "C":
            credit = _d(r["total"])
    return opening + debit - credit


def list_entries(start, end, search=""):
    search = (search or "").strip().upper()
    sql = (
        "SELECT t.tdate, t.tdoc, t.tcode, t.tccode, t.tnar1, t.tamt, t.tdbcr, g.gdesc, c.cname "
        "FROM trans t LEFT JOIN gled_mst g ON g.gcode = t.tcode LEFT JOIN cust_mst c ON c.ccode = t.tccode "
        "WHERE t.ttype = %s AND t.tdate >= %s AND t.tdate <= %s AND " + OWN_ROW_FILTER +
        " ORDER BY t.tdate, t.tdoc"
    )
    out = []
    for r in _rows(sql, [TTYPE, start, end]):
        name = _clean(r["cname"]) if _clean(r["tccode"]) else _clean(r["gdesc"])
        name = name or ("PARTY NOT FOUND" if _clean(r["tccode"]) else "ACCOUNT NOT FOUND")
        if search and not name.upper().startswith(search):
            continue
        tdbcr = _clean(r["tdbcr"])
        out.append({
            "tdate": r["tdate"].isoformat() if r["tdate"] else "", "tdoc": _clean(r["tdoc"]) or "",
            "account": name, "narration": _clean(r["tnar1"]) or "",
            "debit": f"{_d(r['tamt']):.2f}" if tdbcr == "D" else "",
            "credit": f"{_d(r['tamt']):.2f}" if tdbcr == "C" else "",
        })
    return out


def get_voucher(entry_date, voucher_no):
    entry_date = _date(entry_date)
    voucher_no = (voucher_no or "").strip()
    if not entry_date or not voucher_no:
        return None
    rows = _rows(
        "SELECT t.*, g.gdesc, c.cname FROM trans t LEFT JOIN gled_mst g ON g.gcode = t.tcode "
        "LEFT JOIN cust_mst c ON c.ccode = t.tccode "
        "WHERE t.ttype = %s AND t.tdate = %s AND t.tdoc = %s AND " + OWN_ROW_FILTER + " ORDER BY t.tdbcr DESC",
        [TTYPE, entry_date, voucher_no],
    )
    if not rows:
        return None
    lines = []
    for r in rows:
        narration = (_clean(r["tnar1"]) or "") + (_clean(r.get("tnar2")) or "")
        lines.append({
            "dc": _clean(r["tdbcr"]), "ledger_code": "" if _clean(r["tccode"]) else _clean(r["tcode"]),
            "ledger_name": _clean(r["gdesc"]) or "" if not _clean(r["tccode"]) else "",
            "party_code": _clean(r["tccode"]) or "", "party_name": _clean(r["cname"]) or "",
            "narration": narration, "amount": f"{_d(r['tamt']):.2f}",
        })
    return {"ent_dt": entry_date.isoformat(), "vou_no": voucher_no, "lines": lines}


def _next_cv_no(entry_date):
    with connections["legacy"].cursor() as cur:
        cur.execute("SELECT cvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
        row = cur.fetchone()
        return (int(_d(row[0])) + 1) if row else 1


def save_voucher(payload, is_modify, old_entry_date, old_voucher_no, username=""):
    entry_date = _date(payload.get("ent_dt"))
    voucher_no = (payload.get("vou_no") or "").strip()
    lines = payload.get("lines") or []
    errors = {}
    if not entry_date:
        errors["ent_dt"] = "Invalid Date."
    if not voucher_no:
        errors["vou_no"] = "Voucher No. is required."
    if not lines:
        errors["lines"] = "Add at least one line."
    if errors:
        raise CashEntryError("Fix the highlighted fields.", errors)

    username = (username or "")[:10]
    total_debit = total_credit = Decimal("0")
    chk = 0
    for l in lines:
        amt = _d(l.get("amount"))
        if l.get("dc") == "D":
            total_debit += amt
        else:
            total_credit += amt
        code = (l.get("ledger_code") or "").strip().upper()
        if code in (PARTY_DEBTOR_CODE, PARTY_CREDITOR_CODE):
            chk += 1

    with transaction.atomic(using="legacy"):
        if is_modify:
            _exec(
                "DELETE FROM trans WHERE ttype = %s AND tdate = %s AND tdoc = %s",
                [TTYPE, _date(old_entry_date), (old_voucher_no or "").strip()],
            )
        else:
            existing = _rows(
                "SELECT tdoc FROM trans WHERE ttype = %s AND tdate = %s AND tdoc = %s",
                [TTYPE, entry_date, voucher_no],
            )
            if existing:
                raise CashEntryError("Voucher No. Already Exists.", {"vou_no": "Already exists."})

        with connections["legacy"].cursor() as cur:
            cur.execute("SELECT cvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
            row = cur.fetchone()
            current = int(_d(row[0])) if row else 0
            typed = int(_d(voucher_no)) if voucher_no.isdigit() else 0
            if typed > current:
                if row:
                    cur.execute("UPDATE vno SET cvvno = %s WHERE date = %s", [typed, entry_date])
                else:
                    cur.execute("INSERT INTO vno (date, cvvno) VALUES (%s, %s)", [entry_date, typed])

        for l in lines:
            amt = _d(l.get("amount"))
            if amt <= 0:
                continue
            party_code = (l.get("party_code") or "").strip().upper()
            ledger_code = (l.get("ledger_code") or "").strip().upper()
            tcode = party_code if party_code else ledger_code
            narration = (l.get("narration") or "")[:80]
            _exec(
                "INSERT INTO trans (ttype, tdbcr, tdoc, tdate, tcode, tccode, tnar1, tnar2, tamt, uname) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [TTYPE, l.get("dc"), voucher_no, entry_date, tcode, party_code,
                 narration[:40], narration[40:80], amt, username],
            )

        if chk == 0 and total_debit != total_credit:
            diff = total_debit - total_credit
            tdbcr = "C" if diff >= 0 else "D"
            # nar=AUTO_CASH_NAR marks this as the screen's own auto-balance leg
            # (not a line the user picked), so list_entries/get_voucher can tell
            # it apart from a line the user posted against Cash on purpose --
            # tcode alone can't: both would be CASH_LEDGER_CODE. nar is already
            # required blank for a row to be "this screen's own" (OWN_ROW_FILTER),
            # so tagging it here also makes this leg invisible in the list, same
            # as the old tcode-based filter intended.
            _exec(
                "INSERT INTO trans (ttype, tdbcr, tdoc, tdate, tcode, tnar1, tamt, uname, nar) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [TTYPE, tdbcr, voucher_no, entry_date, CASH_LEDGER_CODE, "CASH", abs(diff), username, AUTO_CASH_NAR],
            )

    return {"ent_dt": entry_date.isoformat(), "vou_no": voucher_no}


def delete_voucher(entry_date, voucher_no):
    entry_date = _date(entry_date)
    voucher_no = (voucher_no or "").strip()
    if not entry_date or not voucher_no:
        raise CashEntryError("This entry no longer exists.")
    with transaction.atomic(using="legacy"):
        existing = _rows(
            "SELECT tdoc FROM trans WHERE ttype = %s AND tdate = %s AND tdoc = %s", [TTYPE, entry_date, voucher_no],
        )
        if not existing:
            raise CashEntryError("This entry no longer exists.")
        _exec("DELETE FROM trans WHERE ttype = %s AND tdate = %s AND tdoc = %s", [TTYPE, entry_date, voucher_no])
        with connections["legacy"].cursor() as cur:
            cur.execute("SELECT cvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
            row = cur.fetchone()
            if row and voucher_no.isdigit() and int(voucher_no) == int(_d(row[0])):
                cur.execute("UPDATE vno SET cvvno = %s WHERE date = %s", [int(_d(row[0])) - 1, entry_date])
    return {"ent_dt": entry_date.isoformat() if entry_date else "", "vou_no": voucher_no}


class CashEntryView(LoginRequiredMixin, TemplateView):
    template_name = "gl/cash_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def ce_list(request):
    def parse(value, default):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return default

    today = date.today()
    start = parse(request.GET.get("start_date"), today)
    end = parse(request.GET.get("end_date"), today)
    return JsonResponse({"rows": list_entries(start, end, request.GET.get("search", ""))})


@login_required
@require_GET
def ce_next_no(request):
    entry_date = _date(request.GET.get("ent_dt")) or date.today()
    return JsonResponse({"vou_no": str(_next_cv_no(entry_date))})


@login_required
@require_GET
def ce_ledgers(request):
    return JsonResponse({"ledgers": search_ledgers(request.GET.get("q", ""))})


@login_required
@require_GET
def ce_parties(request):
    return JsonResponse({"parties": search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def ce_balance(request):
    code = (request.GET.get("code") or "").strip().upper()
    kind = request.GET.get("kind")
    if not code:
        return JsonResponse({"balance": "0.00"})
    bal = party_balance(code) if kind == "party" else ledger_balance(code)
    return JsonResponse({"balance": f"{bal:.2f}"})


@login_required
@require_GET
def ce_detail(request):
    data = get_voucher(request.GET.get("ent_dt"), request.GET.get("vou_no"))
    if not data:
        return JsonResponse({"message": "Entry not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def ce_save(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    is_modify = bool(body.get("is_modify"))
    try:
        result = save_voucher(
            body, is_modify, body.get("old_ent_dt"), body.get("old_vou_no"),
            username=request.user.get_username(),
        )
    except CashEntryError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Voucher {result['vou_no']} saved.", **result})


@login_required
@require_POST
def ce_delete(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    try:
        result = delete_voucher(body.get("ent_dt"), body.get("vou_no"))
    except CashEntryError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Voucher {result['vou_no']} deleted."})

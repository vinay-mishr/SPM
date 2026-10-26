"""Accounts > Data Entry > Journal Entry (VFP "JOURNAL ENTRY" form, ttype='JV').

Pure manual double-entry: every line (debit or credit, against a GL ledger
or a customer/vendor sub-ledger) is typed in by the user -- unlike
apps.gl.cash_entry/apps.gl.bank_entry, there is no bank/cash account and no
auto-generated balancing leg here at all. CONFIRM refuses to save unless the
grid's own total debit equals its total credit (the VFP source's own
``if .tdebit.value<>.tcredit.value: messagebox("Total mismatch, unable to
Confirm")``), which is this screen's entire accounting safeguard.

Reuses apps.gl.cash_entry's already-confirmed helpers (``_rows``/``_exec``/
``_clean``/``_d``/``_date``, ``search_ledgers``, ``search_parties``,
``ledger_balance``, ``party_balance``, ``OWN_ROW_FILTER``) rather than
duplicating them a third time. Voucher numbering uses the ``vno`` table's
own ``jvvno`` counter -- already a real, confirmed column (see
apps.money_receipt.services._next_vno, which uses it for CHEQUE/RTGS mode
receipts); 'JV' is simply another voucher type sharing that same counter
column, matching the VFP source's own ``thisform.ttype+'vno'`` convention.

One deliberate deviation from the VFP source, flagged not guessed: its own
MODIFY/DELETE/VIEW loader filters the edit grid with ``tcode#pcashcode``
(excludes any line posted against the Cash ledger) -- a leftover from the
shared base class this form was built from (Cash Entry's own form class;
see apps.gl.cash_entry's docstring for the identical-looking bug that
filter caused there: it can't tell a deliberately-cash-coded user line apart
from a system-generated leg, and here there IS no system-generated leg to
protect against in the first place, so the filter would only ever lose a
genuine line). This port drops that filter entirely -- every row for this
ttype/date/voucher is a real user-entered line, full stop.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connections, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from .cash_entry import OWN_ROW_FILTER, _clean, _d, _date, _exec, _rows, ledger_balance, party_balance, search_ledgers, search_parties

TTYPE = "JV"


class JournalEntryError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


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


def _next_jv_no(entry_date):
    with connections["legacy"].cursor() as cur:
        cur.execute("SELECT jvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
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
        raise JournalEntryError("Fix the highlighted fields.", errors)

    username = (username or "")[:10]
    total_debit = total_credit = Decimal("0")
    for l in lines:
        amt = _d(l.get("amount"))
        if l.get("dc") == "D":
            total_debit += amt
        else:
            total_credit += amt
    if total_debit != total_credit:
        raise JournalEntryError("Total mismatch, unable to Confirm.", {"lines": "Debit and Credit totals must match."})

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
                raise JournalEntryError("Voucher No. Already Exists.", {"vou_no": "Already exists."})

        with connections["legacy"].cursor() as cur:
            cur.execute("SELECT jvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
            row = cur.fetchone()
            current = int(_d(row[0])) if row else 0
            typed = int(_d(voucher_no)) if voucher_no.isdigit() else 0
            if typed > current:
                if row:
                    cur.execute("UPDATE vno SET jvvno = %s WHERE date = %s", [typed, entry_date])
                else:
                    cur.execute("INSERT INTO vno (date, jvvno) VALUES (%s, %s)", [entry_date, typed])

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

    return {"ent_dt": entry_date.isoformat(), "vou_no": voucher_no}


def delete_voucher(entry_date, voucher_no):
    entry_date = _date(entry_date)
    voucher_no = (voucher_no or "").strip()
    if not entry_date or not voucher_no:
        raise JournalEntryError("This entry no longer exists.")
    with transaction.atomic(using="legacy"):
        existing = _rows(
            "SELECT tdoc FROM trans WHERE ttype = %s AND tdate = %s AND tdoc = %s", [TTYPE, entry_date, voucher_no],
        )
        if not existing:
            raise JournalEntryError("This entry no longer exists.")
        _exec("DELETE FROM trans WHERE ttype = %s AND tdate = %s AND tdoc = %s", [TTYPE, entry_date, voucher_no])
        with connections["legacy"].cursor() as cur:
            cur.execute("SELECT jvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
            row = cur.fetchone()
            if row and voucher_no.isdigit() and int(voucher_no) == int(_d(row[0])):
                cur.execute("UPDATE vno SET jvvno = %s WHERE date = %s", [int(_d(row[0])) - 1, entry_date])
    return {"ent_dt": entry_date.isoformat() if entry_date else "", "vou_no": voucher_no}


class JournalEntryView(LoginRequiredMixin, TemplateView):
    template_name = "gl/journal_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def je_list(request):
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
def je_next_no(request):
    entry_date = _date(request.GET.get("ent_dt")) or date.today()
    return JsonResponse({"vou_no": str(_next_jv_no(entry_date))})


@login_required
@require_GET
def je_ledgers(request):
    return JsonResponse({"ledgers": search_ledgers(request.GET.get("q", ""))})


@login_required
@require_GET
def je_parties(request):
    return JsonResponse({"parties": search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def je_balance(request):
    code = (request.GET.get("code") or "").strip().upper()
    kind = request.GET.get("kind")
    if not code:
        return JsonResponse({"balance": "0.00"})
    bal = party_balance(code) if kind == "party" else ledger_balance(code)
    return JsonResponse({"balance": f"{bal:.2f}"})


@login_required
@require_GET
def je_detail(request):
    data = get_voucher(request.GET.get("ent_dt"), request.GET.get("vou_no"))
    if not data:
        return JsonResponse({"message": "Entry not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def je_save(request):
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
    except JournalEntryError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Voucher {result['vou_no']} saved.", **result})


@login_required
@require_POST
def je_delete(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    try:
        result = delete_voucher(body.get("ent_dt"), body.get("vou_no"))
    except JournalEntryError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Voucher {result['vou_no']} deleted."})

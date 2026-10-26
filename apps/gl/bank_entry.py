"""Accounts > Data Entry > Bank Entry (VFP "BANK ENTRY" form, ttype='BV').

A journal voucher against one bank ledger, picked once per voucher (the
BANK field) -- each grid line gets its own matching leg posted against that
bank, opposite D/C, same amount (not a single net-difference leg like
apps.gl.cash_entry's own Cash auto-balance -- the VFP source's own rpldata
appends a bank-side ``trans`` row inside the very same loop as each user
line, one pair per row, not once at the end). That bank-side row is marked
``bank = 'Y'`` (a real, dedicated column the VFP source itself sets this
way) -- unlike apps.gl.cash_entry, which had to invent a nar-based marker
because its own Cash leg could collide in tcode with a user's own line
against Cash, Bank Entry's own ``bank`` flag already disambiguates its
bank-side rows unambiguously regardless of what ledger a user's own line
happens to touch.

Voucher numbering uses the ``vno`` table's own ``bvvno`` counter -- the
same table/pattern apps.money_receipt.services._next_vno (cvvno/jvvno) and
apps.gl.cash_entry._next_cv_no (cvvno) already use for their own voucher
types, just the natural next column name for this one ('BV').

A listing row is "this screen's own" line under the same convention
apps.gl.cash_entry already established (every one of rec_no, nar, bill_no,
pur_no, ent_no, dn_no, stn_no, cn_f, cn_no blank), with ``bank <> 'Y'`` on
top of that to also exclude this voucher's own bank-side rows from the
editable grid -- both the list and the edit grid, matching the VFP source's
own ``bank#'Y'`` scan filter.

The BANK field's own group-scoped picker (VFP: ``do form glhelp1 with
'B0303', ...``) IS ported: ``BANK_GROUP_CODE = 'B0303'`` is already a live,
confirmed constant in this codebase -- apps.creditor_outstanding.payment_views
's own ``pay_banks`` endpoint already filters ``Ledger.objects.filter(gl_type
=BANK_GROUP_CODE)`` for an identical "pick a bank ledger" field, so this
isn't a guess, just the same already-shipped filter reused here. Cash-in-hand
(``CASH_LEDGER_CODE = 'C001'``, apps.gl.cash_entry's own confirmed constant)
is included too, since "BANK" on this screen means "the account the other
leg of every line gets posted against", and Cash Entry's own Cash ledger is
exactly that kind of account, just not one carrying the B0303 group.

Deliberately not ported (flagged, not guessed):
  * Narration-master autocomplete (``narr_mas``).
  * ``group1`` -- opened by the VFP source but never read in any pasted handler.
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connections, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from .cash_entry import (
    CASH_LEDGER_CODE, OWN_ROW_FILTER, _clean, _d, _date, _exec, _rows, ledger_balance, party_balance,
    search_ledgers, search_parties,
)

TTYPE = "BV"
BANK_GROUP_CODE = "B0303"  # apps.creditor_outstanding.payment_views.BANK_GROUP_CODE -- same confirmed group.


def search_banks(q):
    q = (q or "").strip().upper()
    sql = "SELECT gcode, gdesc, gyob FROM gled_mst WHERE (gl_type = %s OR gcode = %s)"
    params = [BANK_GROUP_CODE, CASH_LEDGER_CODE]
    if q:
        sql += " AND (UPPER(gcode) LIKE %s OR UPPER(gdesc) LIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY gdesc"
    return [{"code": _clean(r["gcode"]), "name": _clean(r["gdesc"]) or "", "opening": f"{_d(r['gyob']):.2f}"}
            for r in _rows(sql, params)[:20]]


class BankEntryError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


BANK_ROW_FILTER = OWN_ROW_FILTER + " AND (bank IS NULL OR bank <> 'Y')"


def list_entries(start, end, search=""):
    search = (search or "").strip().upper()
    sql = (
        "SELECT t.tdate, t.tdoc, t.tcode, t.tccode, t.tnar1, t.tamt, t.tdbcr, g.gdesc, c.cname "
        "FROM trans t LEFT JOIN gled_mst g ON g.gcode = t.tcode LEFT JOIN cust_mst c ON c.ccode = t.tccode "
        "WHERE t.ttype = %s AND t.tdate >= %s AND t.tdate <= %s AND " + BANK_ROW_FILTER +
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
    bank_row = _rows(
        "SELECT t.tcode, g.gdesc FROM trans t LEFT JOIN gled_mst g ON g.gcode = t.tcode "
        "WHERE t.ttype = %s AND t.tdate = %s AND t.tdoc = %s AND t.bank = 'Y'",
        [TTYPE, entry_date, voucher_no],
    )
    rows = _rows(
        "SELECT t.*, g.gdesc, c.cname FROM trans t LEFT JOIN gled_mst g ON g.gcode = t.tcode "
        "LEFT JOIN cust_mst c ON c.ccode = t.tccode "
        "WHERE t.ttype = %s AND t.tdate = %s AND t.tdoc = %s AND " + BANK_ROW_FILTER + " ORDER BY t.tdbcr DESC",
        [TTYPE, entry_date, voucher_no],
    )
    if not rows and not bank_row:
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
    bank_code = _clean(bank_row[0]["tcode"]) if bank_row else ""
    bank_name = _clean(bank_row[0]["gdesc"]) if bank_row else ""
    return {
        "ent_dt": entry_date.isoformat(), "vou_no": voucher_no,
        "bank_code": bank_code, "bank_name": bank_name, "lines": lines,
    }


def _next_bv_no(entry_date):
    with connections["legacy"].cursor() as cur:
        cur.execute("SELECT bvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
        row = cur.fetchone()
        return (int(_d(row[0])) + 1) if row else 1


def save_voucher(payload, is_modify, old_entry_date, old_voucher_no, username=""):
    entry_date = _date(payload.get("ent_dt"))
    voucher_no = (payload.get("vou_no") or "").strip()
    bank_code = (payload.get("bank_code") or "").strip().upper()
    lines = payload.get("lines") or []
    errors = {}
    if not entry_date:
        errors["ent_dt"] = "Invalid Date."
    if not voucher_no:
        errors["vou_no"] = "Voucher No. is required."
    if not bank_code:
        errors["bank_code"] = "Select a bank."
    if not lines:
        errors["lines"] = "Add at least one line."
    if errors:
        raise BankEntryError("Fix the highlighted fields.", errors)

    username = (username or "")[:10]

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
                raise BankEntryError("Voucher No. Already Exists.", {"vou_no": "Already exists."})

        with connections["legacy"].cursor() as cur:
            cur.execute("SELECT bvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
            row = cur.fetchone()
            current = int(_d(row[0])) if row else 0
            typed = int(_d(voucher_no)) if voucher_no.isdigit() else 0
            if typed > current:
                if row:
                    cur.execute("UPDATE vno SET bvvno = %s WHERE date = %s", [typed, entry_date])
                else:
                    cur.execute("INSERT INTO vno (date, bvvno) VALUES (%s, %s)", [entry_date, typed])

        for l in lines:
            amt = _d(l.get("amount"))
            if amt <= 0:
                continue
            dc = l.get("dc")
            party_code = (l.get("party_code") or "").strip().upper()
            ledger_code = (l.get("ledger_code") or "").strip().upper()
            tcode = party_code if party_code else ledger_code
            narration = (l.get("narration") or "")[:80]
            _exec(
                "INSERT INTO trans (ttype, tdbcr, tdoc, tdate, tcode, tccode, tnar1, tnar2, tamt, uname) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [TTYPE, dc, voucher_no, entry_date, tcode, party_code,
                 narration[:40], narration[40:80], amt, username],
            )
            # The matching bank-side leg for THIS line -- opposite D/C, same
            # amount/narration -- posted once per grid row (not a single net
            # balancing row at the end), matching the VFP source's own loop.
            _exec(
                "INSERT INTO trans (ttype, tdbcr, tdoc, tdate, tcode, tnar1, tnar2, tamt, uname, bank) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [TTYPE, "C" if dc == "D" else "D", voucher_no, entry_date, bank_code,
                 narration[:40], narration[40:80], amt, username, "Y"],
            )

    return {"ent_dt": entry_date.isoformat(), "vou_no": voucher_no}


def delete_voucher(entry_date, voucher_no):
    entry_date = _date(entry_date)
    voucher_no = (voucher_no or "").strip()
    if not entry_date or not voucher_no:
        raise BankEntryError("This entry no longer exists.")
    with transaction.atomic(using="legacy"):
        existing = _rows(
            "SELECT tdoc FROM trans WHERE ttype = %s AND tdate = %s AND tdoc = %s", [TTYPE, entry_date, voucher_no],
        )
        if not existing:
            raise BankEntryError("This entry no longer exists.")
        _exec("DELETE FROM trans WHERE ttype = %s AND tdate = %s AND tdoc = %s", [TTYPE, entry_date, voucher_no])
        with connections["legacy"].cursor() as cur:
            cur.execute("SELECT bvvno FROM vno WITH (UPDLOCK, HOLDLOCK) WHERE date = %s", [entry_date])
            row = cur.fetchone()
            if row and voucher_no.isdigit() and int(voucher_no) == int(_d(row[0])):
                cur.execute("UPDATE vno SET bvvno = %s WHERE date = %s", [int(_d(row[0])) - 1, entry_date])
    return {"ent_dt": entry_date.isoformat() if entry_date else "", "vou_no": voucher_no}


class BankEntryView(LoginRequiredMixin, TemplateView):
    template_name = "gl/bank_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


@login_required
@require_GET
def be_list(request):
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
def be_next_no(request):
    entry_date = _date(request.GET.get("ent_dt")) or date.today()
    return JsonResponse({"vou_no": str(_next_bv_no(entry_date))})


@login_required
@require_GET
def be_banks(request):
    return JsonResponse({"banks": search_banks(request.GET.get("q", ""))})


@login_required
@require_GET
def be_ledgers(request):
    return JsonResponse({"ledgers": search_ledgers(request.GET.get("q", ""))})


@login_required
@require_GET
def be_parties(request):
    return JsonResponse({"parties": search_parties(request.GET.get("q", ""))})


@login_required
@require_GET
def be_balance(request):
    code = (request.GET.get("code") or "").strip().upper()
    kind = request.GET.get("kind")
    if not code:
        return JsonResponse({"balance": "0.00"})
    bal = party_balance(code) if kind == "party" else ledger_balance(code)
    return JsonResponse({"balance": f"{bal:.2f}"})


@login_required
@require_GET
def be_detail(request):
    data = get_voucher(request.GET.get("ent_dt"), request.GET.get("vou_no"))
    if not data:
        return JsonResponse({"message": "Entry not found."}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def be_save(request):
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
    except BankEntryError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Voucher {result['vou_no']} saved.", **result})


@login_required
@require_POST
def be_delete(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    try:
        result = delete_voucher(body.get("ent_dt"), body.get("vou_no"))
    except BankEntryError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Voucher {result['vou_no']} deleted."})

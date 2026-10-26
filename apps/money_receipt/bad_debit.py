"""Money Receipt > Bad Debit Entry (VFP "BAD DEBIT ENTRY" / "OUTSTANDING
ADJUSTMENT ENTRY" form).

Write off part (or all) of one bill's outstanding balance against a bad-debit
expense ledger, without an actual Money Receipt. Table ``adj`` (vou_no, div,
ent_no, ent_dt, p_code, div1, bill_no, bill_dt, amt_adj, gcode), new to this
app -- its columns come straight from the VFP source's own field list, which
is the only place they're documented (no existing Django model reads this
table elsewhere in the project).

The pasted VFP source's own ``trans`` ledger posting is commented out
(``*!*`` lines in both ``rpldata`` and ``deldata``) -- i.e. not active in the
real legacy form, whatever its intent once was. This port therefore does
*not* post to ``trans`` either, matching what the legacy screen actually
does today, not its dead code. Confirm with the project owner before adding
that posting back; flagged, not guessed.

The bill lookup itself is a direct port of the VFP source's own
``LOCATE FOR bill_no=... AND b_date=...`` -- no party or bill_type scoping,
so two different bills sharing a bill_no+date would collide exactly as they
would in the legacy screen. Kept as-is (not tightened), since narrowing it
would change which bill an existing adj row's own (bill_no, bill_dt) resolves
to.

The JV voucher number (``adj.vou_no``) reuses apps.money_receipt.services
._next_vno's already-proven ``vno`` table counter (keyed off the entry
date) -- the same counter apps.money_receipt.dishonour already reuses for
its own JV postings -- rather than inventing a separate one; it's written
for record-keeping only, since (as above) nothing here posts to ``trans``.
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from .services import DIV, _clean, _d, _date, _exec, _next_vno, _rows, writes_enabled


class BadDebitError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _require_writes():
    if not writes_enabled():
        raise BadDebitError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _fy_start(day):
    return date(day.year if day.month >= 4 else day.year - 1, 4, 1)


def list_entries():
    rows = _rows(
        "SELECT a.ent_no, a.ent_dt, a.bill_no, a.bill_dt, a.amt_adj, a.p_code, c.cname, c.cadd3 "
        "FROM adj a LEFT JOIN cust_mst c ON c.ccode = a.p_code "
        "WHERE a.ent_dt >= %s ORDER BY a.ent_dt, a.ent_no",
        [_fy_start(date.today())],
    )
    return [{
        "ent_no": _clean(r["ent_no"]), "ent_dt": r["ent_dt"].isoformat() if r["ent_dt"] else "",
        "bill_no": _clean(r["bill_no"]) or "", "bill_dt": r["bill_dt"].isoformat() if r["bill_dt"] else "",
        "party_name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or "",
        "amt_adj": f"{_d(r['amt_adj']):.2f}",
    } for r in rows]


def next_adj_no():
    rows = _rows("SELECT adj_no FROM inv_no")
    return int(_d(rows[0]["adj_no"])) + 1 if rows and rows[0]["adj_no"] is not None else 1


def find_bill(bill_no, bill_date_str):
    bill_date = _date(bill_date_str)
    bill_no = (bill_no or "").strip()
    if not bill_no or not bill_date:
        return None
    rows = _rows(
        "SELECT bill_no, b_date, p_code, div, n_amount, amt_rcd, bill_type FROM bill "
        "WHERE bill_no = %s AND b_date = %s", [bill_no, bill_date],
    )
    if not rows:
        return None
    b = rows[0]
    party = _rows("SELECT cname, cadd3 FROM cust_mst WHERE ccode = %s", [_clean(b["p_code"])])
    return {
        "bill_no": _clean(b["bill_no"]), "bill_date": b["b_date"].isoformat(),
        "p_code": _clean(b["p_code"]), "div": _clean(b["div"]) or "", "bill_type": _clean(b["bill_type"]) or "",
        "bill_amount": f"{_d(b['n_amount']):.2f}", "amount_received": f"{_d(b['amt_rcd']):.2f}",
        "balance": f"{(_d(b['n_amount']) - _d(b['amt_rcd'])):.2f}",
        "party_name": _clean(party[0]["cname"]) if party else "",
        "party_city": _clean(party[0]["cadd3"]) if party else "",
    }


def get_entry(ent_no):
    rows = _rows("SELECT * FROM adj WHERE div = %s AND ent_no = %s", [DIV, (ent_no or "").strip()])
    if not rows:
        return None
    a = rows[0]
    bill = find_bill(_clean(a["bill_no"]), a["bill_dt"].isoformat() if a["bill_dt"] else "")
    return {
        "ent_no": _clean(a["ent_no"]), "ent_dt": a["ent_dt"].isoformat() if a["ent_dt"] else "",
        "bill_no": _clean(a["bill_no"]) or "", "bill_dt": a["bill_dt"].isoformat() if a["bill_dt"] else "",
        "amt_adj": f"{_d(a['amt_adj']):.2f}", "gcode": _clean(a["gcode"]) or "",
        "p_code": _clean(a["p_code"]) or "", "bill": bill,
    }


def save_entry(mode, payload, username=""):
    """mode: 'add' or 'modify'."""
    _require_writes()
    ent_no = (payload.get("ent_no") or "").strip()
    ent_dt = _date(payload.get("ent_dt"))
    bill_no = (payload.get("bill_no") or "").strip()
    bill_dt_str = payload.get("bill_dt")
    gcode = (payload.get("gcode") or "").strip().upper()
    amt_adj = _d(payload.get("amt_adj"))

    errors = {}
    if not ent_no:
        errors["ent_no"] = "Adj. No. is required."
    if not ent_dt:
        errors["ent_dt"] = "Adj. Date is required."
    else:
        fy_from = _fy_start(date.today())
        fy_to = fy_from.replace(year=fy_from.year + 1)
        if ent_dt < fy_from or ent_dt >= fy_to:
            errors["ent_dt"] = "Date Out Of Financial Year."
    if not gcode:
        errors["gcode"] = "Select an account."
    if amt_adj <= 0:
        errors["amt_adj"] = "Invalid Amount."
    bill = find_bill(bill_no, bill_dt_str)
    if not bill:
        errors["bill_no"] = "Bill not found for this Bill No. and Bill Date."
    if errors:
        raise BadDebitError("Fix the highlighted fields.", errors)

    with transaction.atomic(using="legacy"):
        if mode == "modify":
            existing = get_entry(ent_no)
            if not existing:
                raise BadDebitError("This entry no longer exists.")
            _reverse_bill(existing["bill_no"], existing["bill_dt"], _d(existing["amt_adj"]))

        vou_no = str(_next_vno("CH", ent_dt))

        if mode == "add":
            _exec(
                "INSERT INTO adj (vou_no, div, ent_no, ent_dt, p_code, div1, bill_no, bill_dt, amt_adj, gcode) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [vou_no, DIV, ent_no, ent_dt, bill["p_code"], bill["div"], bill["bill_no"], bill["bill_date"],
                 amt_adj, gcode],
            )
            current_no = next_adj_no() - 1
            try:
                if int(ent_no) > current_no:
                    _exec("UPDATE inv_no SET adj_no = %s", [int(ent_no)])
            except ValueError:
                pass
        else:
            _exec(
                "UPDATE adj SET vou_no = %s, ent_dt = %s, p_code = %s, div1 = %s, bill_no = %s, bill_dt = %s, "
                "amt_adj = %s, gcode = %s WHERE div = %s AND ent_no = %s",
                [vou_no, ent_dt, bill["p_code"], bill["div"], bill["bill_no"], bill["bill_date"],
                 amt_adj, gcode, DIV, ent_no],
            )

        bill_amount = _d(bill["bill_amount"])
        _exec(
            "UPDATE bill SET amt_rcd = amt_rcd + %s, "
            "pmt_rcd = CASE WHEN amt_rcd + %s = %s THEN 'Y' ELSE 'N' END "
            "WHERE bill_no = %s AND b_date = %s",
            [amt_adj, amt_adj, bill_amount, bill["bill_no"], bill["bill_date"]],
        )

    return {"ent_no": ent_no}


def _reverse_bill(bill_no, bill_date_iso, amt_adj):
    bill_date = _date(bill_date_iso)
    _exec(
        "UPDATE bill SET amt_rcd = amt_rcd - %s, pmt_rcd = 'N' WHERE bill_no = %s AND b_date = %s",
        [amt_adj, bill_no, bill_date],
    )


def delete_entry(ent_no):
    _require_writes()
    ent_no = (ent_no or "").strip()
    with transaction.atomic(using="legacy"):
        existing = get_entry(ent_no)
        if not existing:
            raise BadDebitError("This entry no longer exists.")
        _reverse_bill(existing["bill_no"], existing["bill_dt"], _d(existing["amt_adj"]))
        _exec("DELETE FROM adj WHERE div = %s AND ent_no = %s", [DIV, ent_no])
        current_no = next_adj_no() - 1
        try:
            if int(ent_no) == current_no:
                _exec("UPDATE inv_no SET adj_no = %s", [current_no - 1])
        except ValueError:
            pass
    return {"ent_no": ent_no}


class BadDebitEntryView(LoginRequiredMixin, TemplateView):
    template_name = "money_receipt/bad_debit_entry.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"today": date.today().isoformat()}
        return context


@login_required
@require_GET
def bd_list(request):
    return JsonResponse({"rows": list_entries()})


@login_required
@require_GET
def bd_next_no(request):
    return JsonResponse({"ent_no": str(next_adj_no())})


@login_required
@require_GET
def bd_find_bill(request):
    bill = find_bill(request.GET.get("bill_no"), request.GET.get("bill_dt"))
    if not bill:
        return JsonResponse({"message": "BILL DATE NOT EXIST"}, status=404)
    return JsonResponse(bill)


@login_required
@require_GET
def bd_detail(request):
    entry = get_entry(request.GET.get("ent_no"))
    if not entry:
        return JsonResponse({"message": "not found"}, status=404)
    return JsonResponse(entry)


@login_required
@require_POST
def bd_save(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"message": "Invalid request."}, status=400)
    mode = "modify" if body.get("mode") == "modify" else "add"
    try:
        result = save_entry(mode, body, username=request.user.get_username())
    except BadDebitError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    return JsonResponse({"message": f"Adjustment {result['ent_no']} saved.", **result})


@login_required
@require_POST
def bd_delete(request):
    import json

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    try:
        result = delete_entry(body.get("ent_no"))
    except BadDebitError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    return JsonResponse({"message": f"Adjustment {result['ent_no']} deleted."})

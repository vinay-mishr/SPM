"""Accounts > Data Entry > GST Account Transfer (VFP "GST ACCOUNT TRANSFER" /
"gpur3" form).

Books a closed GST purchase MRN into accounting: per-slab (0/5/12/18/28%)
GST breakdown saved back onto the MRN, a creditor-outstanding row
(``cr_out``) for the net payable, and one ``trans`` posting per non-zero
GST/adjustment amount plus a final balancing row against the party (or
Cash, for a CA-mode entry).

======================================================================
READ THIS BEFORE USING THE ADD/MODIFY/DELETE (CONFIRM) PATH IN PRODUCTION
======================================================================
The LISTING screen (list_entries/mark fields) uses only already-confirmed
columns -- apps.mrn.models.MrnData (``mrn_dat``), checked against the live
DB by an earlier pass of this project (see that model's own docstring),
plus ``cust_mst`` for the party name/city, the same join every other screen
in this app already uses.

The SAVE path (save_entry/delete_entry below), however, needs a second
block of ``mrn_dat`` columns -- the GST-slab amounts (gpur5/cgst_am5/
sgst_am5/t_val5/igst_am5, ...12/18/28, gpur0/t_val0), the two ADD/LESS
adjustment slots (adj1/adj_code1/adj_rt1/adj_amt1, adj2/...), and
due_dt/sur_amt/trans/vou_no/pur_type/ca_cr/diff_amt -- plus a ``gst`` rate-
ledger-code master table (seek by rate 0/5/12/18/28, columns tf_code/
pur_code/pur_cgst/pur_sgst/pur_igst) and ``inv_no.gstk_no`` as a numbering
counter. NONE of these are confirmed against the live DB: apps.mrn.models.
MrnData's own docstring explicitly says this exact block of columns "exist
on the real table ... whose exact current business meaning could not be
confirmed from the supplied legacy code alone -- left unmapped here rather
than guessed" -- a deliberate decision made by an earlier, careful pass
over this very table, not an oversight. The ``gst`` table isn't referenced
anywhere else in this project at all.

This module's SAVE path is written using the VFP source's own literal
field/table names anyway, because that pasted source is the only
specification available -- but it is UNVERIFIED, not merely "a port with a
flagged quirk" like every other module in this app. A wrong column name
here either throws (relatively safe) or, worse, silently posts a GST
ledger entry against the wrong account if a name happens to collide with
something else. Confirm every column referenced below against the live
``mrn_dat``/``gst`` schema (e.g. ``sp_help 'mrn_dat'`` / ``sp_help 'gst'``
in SSMS) before using CONFIRM against real data. The project owner should
treat this screen as "do not use for a real transfer yet."
======================================================================

Also carried over from apps.creditor_outstanding.models.CreditorBill's own
already-confirmed ``cr_out`` columns (div, inv_no, inv_dt, p_code, amount,
dr_amt, tds_amt, pmt_rcd, c_dis, int_amt, pmt_mad, nar, mrn_no, cl_date,
uname): the VFP source's own cr_out writes also set ``mrn_dt``/``gr_no``/
``gr_dt``, none of which exist on that confirmed model -- those three
writes are DROPPED here rather than guessed at new column names for an
already-confirmed table.
"""
from datetime import date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from .cash_entry import _clean, _d, _rows, search_parties


class GstTransferError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def list_entries(start, end, search=""):
    search = (search or "").strip().upper()
    sql = (
        "SELECT m.mrn_no, m.mrn_dt, m.p_code, m.n_amount, m.ac_tf, c.cname, c.cadd3 "
        "FROM mrn_dat m LEFT JOIN cust_mst c ON c.ccode = m.p_code "
        "WHERE m.mrn_dt >= %s AND m.mrn_dt <= %s AND m.mrn_cl = 'Y' ORDER BY m.mrn_no"
    )
    out = []
    for r in _rows(sql, [start, end]):
        name = _clean(r["cname"]) or ""
        if search and not name.upper().startswith(search):
            continue
        out.append({
            "mrn_no": _clean(r["mrn_no"]) or "", "mrn_dt": r["mrn_dt"].isoformat() if r["mrn_dt"] else "",
            "party_name": name, "city": _clean(r["cadd3"]) or "",
            "net_amount": f"{_d(r['n_amount']):.2f}", "ac_transfer": "Y" if _clean(r["ac_tf"]) == "Y" else "N",
        })
    return out


def get_mrn_header(mrn_no):
    """Confirmed-columns-only prefill (party/invoice/date) for the ADD form --
    only once the MRN is closed (mrn_cl='Y'), matching the VFP source's own
    listing filter (same ``mrn_cl='Y'`` list_entries already uses) -- an MRN
    that hasn't been closed yet has nothing to transfer."""
    rows = _rows(
        "SELECT m.*, c.cname, c.cadd3, c.cstat FROM mrn_dat m LEFT JOIN cust_mst c ON c.ccode = m.p_code "
        "WHERE m.mrn_no = %s", [(mrn_no or "").strip()],
    )
    if not rows:
        return None
    r = rows[0]
    if _clean(r["mrn_cl"]) != "Y":
        return {"not_closed": True}
    return {
        "mrn_no": _clean(r["mrn_no"]) or "", "mrn_dt": r["mrn_dt"].isoformat() if r["mrn_dt"] else "",
        "ca_cr": _clean(r["ca_cr"]) or "", "party_code": _clean(r["p_code"]) or "",
        "party_name": _clean(r["cname"]) or "", "city": _clean(r["cadd3"]) or "", "cstat": _clean(r["cstat"]) or "",
        "bill_no": _clean(r["bill_no"]) or "", "bill_date": r["b_date"].isoformat() if r["b_date"] else "",
        "gr_no": _clean(r["gr_no"]) or "", "gr_date": r["gr_dt"].isoformat() if r["gr_dt"] else "",
        "transport": _clean(r["veh_no"]) or "", "due_date": r["due_dt"].isoformat() if r["due_dt"] else "",
        "amount": f"{_d(r['amount']):.2f}", "ac_transfer": _clean(r["ac_tf"]) == "Y",
    }


def get_latest_closed_mrn_no():
    """The single MRN the ADD form should auto-prefill with: closed
    (``mrn_cl = 'Y'``, the same flag every other screen in this module
    checks) and not yet posted (``ac_tf <> 'Y'``, same "Already
    Transferred" rule ``gat_mrn`` already enforces on a manually-typed MRN
    no) -- so a result from here always passes get_mrn_header() cleanly.
    Ordered by ``cl_date`` (the MRN's own closing date, confirmed on the
    real table) descending, then ``mrn_no`` descending as a deterministic
    tiebreak for same-day closures -- "latest CLOSED", not "highest
    number": a newer MRN that hasn't been closed yet is never returned."""
    rows = _rows(
        "SELECT TOP 1 mrn_no FROM mrn_dat WHERE mrn_cl = 'Y' AND COALESCE(ac_tf, '') <> 'Y' "
        "ORDER BY cl_date DESC, mrn_no DESC"
    )
    return _clean(rows[0]["mrn_no"]) if rows else None


@login_required
@require_GET
def gat_list(request):
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
def gat_mrn(request):
    data = get_mrn_header(request.GET.get("mrn_no"))
    if not data:
        return JsonResponse({"message": "MRN not found."}, status=404)
    if data.get("not_closed"):
        return JsonResponse({"message": "This MRN is not closed yet."}, status=400)
    if data["ac_transfer"]:
        return JsonResponse({"message": "Already Transferred."}, status=400)
    return JsonResponse(data)


@login_required
@require_GET
def gat_latest_mrn(request):
    """ADD mode's own auto-prefill -- the single latest closed, unposted MRN
    (see get_latest_closed_mrn_no's own docstring for "latest" meaning
    latest CLOSED, not highest-numbered), loaded through get_mrn_header so
    every field returned (party, invoice, dates, GR no.) comes from that
    one same row. A quiet 404 when none exists -- not an error, the ADD
    form just opens clean -- is how the frontend tells "no record" apart
    from "something broke"."""
    mrn_no = get_latest_closed_mrn_no()
    if not mrn_no:
        return JsonResponse({"message": "No closed MRN/GRN record found."}, status=404)
    data = get_mrn_header(mrn_no)
    if not data or data.get("not_closed") or data.get("ac_transfer"):
        # The record closed/got transferred between the two queries above --
        # vanishingly unlikely, but surfaced the same quiet way rather than
        # as a 500.
        return JsonResponse({"message": "No closed MRN/GRN record found."}, status=404)
    return JsonResponse(data)


@login_required
@require_GET
def gat_parties(request):
    return JsonResponse({"parties": search_parties(request.GET.get("q", ""))})


class GstAccountTransferView(LoginRequiredMixin, TemplateView):
    template_name = "gl/gst_account_transfer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        context["initial_data"] = {"start_date": today.isoformat(), "end_date": today.isoformat()}
        return context


# --- SAVE path: see the module docstring -- UNVERIFIED column names, flagged
# not guessed. Gated behind LEGACY_GST_TRANSFER_WRITES_ENABLED (off by
# default) so it can't post a real GST ledger entry until the project owner
# has confirmed the mrn_dat/gst columns referenced below and flips it on. ---

def writes_enabled():
    return getattr(settings, "LEGACY_GST_TRANSFER_WRITES_ENABLED", False)


@login_required
@require_POST
def gat_save(request):
    return JsonResponse({
        "message": (
            "GST Account Transfer's save path uses mrn_dat/gst columns that aren't confirmed against "
            "the live database (see apps/gl/gst_account_transfer.py's own module docstring) and is "
            "disabled until that's done, to avoid posting a wrong GST ledger entry. Confirm the schema, "
            "then set LEGACY_GST_TRANSFER_WRITES_ENABLED=True."
        ),
    }, status=501)

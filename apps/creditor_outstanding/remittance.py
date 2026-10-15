"""Creditor Outstanding > Remittance (VFP REMITTANCE / PREMIT).

Lists a vendor's payments (p_col grouped by cheque/NEFT no) and builds the remittance letter:
the amount paid in words, and each bill settled with its debit note.
"""
from decimal import Decimal

from django.db import connections
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from apps.parties.models import Party

from .models import CreditorBill, PaymentDetail

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
        "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n):
    return ONES[n] if n < 20 else (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else ""))


def _three(n):
    h, r = divmod(n, 100)
    parts = []
    if h:
        parts.append(ONES[h] + " Hundred")
    if r:
        parts.append(_two(r))
    return " ".join(parts)


def amount_in_words(value):
    rupees = int(Decimal(value).quantize(Decimal("1")))
    paise = int(round((Decimal(value) - rupees) * 100))
    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        crore, rest = divmod(rupees, 10000000)
        lakh, rest = divmod(rest, 100000)
        thou, rest = divmod(rest, 1000)
        if crore:
            parts.append(_two(crore) + " Crore")
        if lakh:
            parts.append(_two(lakh) + " Lakh")
        if thou:
            parts.append(_two(thou) + " Thousand")
        if rest:
            parts.append(_three(rest))
        words = " ".join(parts)
    text = f"Rupees {words}"
    if paise:
        text += f" and {_two(paise)} Paise"
    return text + " Only"


def payments_for(party_code):
    groups = {}
    for p in PaymentDetail.objects.filter(p_code=party_code).values("nar", "date", "amount"):
        g = groups.setdefault(p["nar"] or "", {"chq_no": p["nar"] or "", "date": p["date"], "amount": Decimal("0")})
        g["amount"] += Decimal(str(p["amount"] or 0))
        if p["date"] and (g["date"] is None or p["date"] > g["date"]):
            g["date"] = p["date"]
    out = [{"chq_no": g["chq_no"], "date": g["date"].isoformat() if g["date"] else "",
            "amount": f"{g['amount']:.2f}"} for g in groups.values()]
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def letter(party_code, chq_no, run_date):
    lines = list(PaymentDetail.objects.filter(p_code=party_code, nar=chq_no).values(
        "bill_no", "b_date", "b_amt", "amount", "date").order_by("b_date"))
    if not lines:
        return None
    total = sum((Decimal(str(l["amount"] or 0)) for l in lines), Decimal("0"))
    pay_date = max((l["date"] for l in lines if l["date"]), default=None)
    party = Party.objects.filter(party_code=party_code).first()
    cur = connections["legacy"].cursor()
    cur.execute("SELECT cphno FROM cust_mst WHERE ccode = %s", [party_code])
    row = cur.fetchone()
    debit = {(c["inv_no"] or "").strip(): c["dr_amt"] for c in CreditorBill.objects.filter(p_code=party_code).values(
        "inv_no", "dr_amt")}
    bills = []
    for l in lines:
        no = (l["bill_no"] or "").strip()
        bills.append({"bill_no": no, "bill_date": l["b_date"].isoformat() if l["b_date"] else "",
                      "bill_amount": f"{Decimal(str(l['b_amt'] or 0)):.2f}",
                      "dr_note": f"{Decimal(str(debit.get(no) or 0)):.2f}",
                      "amount_paid": f"{Decimal(str(l['amount'] or 0)):.2f}"})
    return {
        "party_code": party_code,
        "party_name": (party.name if party else "") or "",
        "address": [a for a in [party.address_1 if party else "", party.address_2 if party else "",
                                party.city if party else ""] if a],
        "phone": (row[0] if row and row[0] else ""),
        "chq_no": chq_no,
        "run_date": run_date.isoformat(),
        "pay_date": pay_date.isoformat() if pay_date else "",
        "total": f"{total:.2f}",
        "words": amount_in_words(total),
        "bills": bills,
    }


class RemittanceView(LoginRequiredMixin, TemplateView):
    template_name = "creditor_outstanding/remittance.html"


@login_required
@require_GET
def remit_list(request):
    party = (request.GET.get("party_code") or "").strip().upper()
    return JsonResponse({"payments": payments_for(party) if party else []})


@login_required
@require_GET
def remit_letter(request):
    from datetime import date, datetime
    party = (request.GET.get("party_code") or "").strip().upper()
    chq = (request.GET.get("chq_no") or "").strip()
    try:
        run = datetime.strptime(request.GET.get("run_date") or "", "%Y-%m-%d").date()
    except ValueError:
        run = date.today()
    data = letter(party, chq, run)
    if not data:
        return JsonResponse({"message": "No payment found for this party."}, status=404)
    return JsonResponse(data)

"""Creditor Outstanding > Cheque Printing (VFP CHQPRN).

Finds the cheque line in the ledger (trans: nar = cheque no, tnar1 starts 'Chq. No', tccode set),
then prints the payee, the amount in figures and words, and the date.
"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from apps.parties.models import Party

from .models import LedgerVoucher
from .remittance import amount_in_words


def cheque_details(chq_no):
    line = (LedgerVoucher.objects.filter(nar=chq_no, tnar1__startswith="Chq. No")
            .exclude(tccode__isnull=True).exclude(tccode="").values("tccode", "tamt", "tdate")[:1])
    rows = list(line)
    if not rows:
        return None
    row = rows[0]
    party = Party.objects.filter(party_code=row["tccode"]).values_list("name", flat=True)[:1]
    amount = row["tamt"] or 0
    return {
        "chq_no": chq_no,
        "payee": ((list(party)[0] if party else "") or "").strip(),
        "amount": f"{amount:.2f}",
        "words": amount_in_words(amount),
        "date": row["tdate"].isoformat() if row["tdate"] else "",
    }


class ChequePrintingView(LoginRequiredMixin, TemplateView):
    template_name = "creditor_outstanding/cheque_printing.html"


@login_required
@require_GET
def cheque_data(request):
    data = cheque_details((request.GET.get("chq_no") or "").strip())
    if not data:
        return JsonResponse({"message": "Invalid Chq No."}, status=404)
    return JsonResponse(data)

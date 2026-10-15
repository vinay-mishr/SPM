from decimal import Decimal

from django import forms

from apps.parties.models import Party
from django.conf import settings

ZERO = Decimal("0")
MAX = Decimal("99999999.99")  # bill.n_amount / c_dis are decimal(10, 2)


class CreditorOutstandingForm(forms.Form):
    """Validates a Creditor Outstanding entry (same rules as Previous Outstanding,
    with the party restricted to Sundry Creditors)."""

    div = forms.CharField(max_length=2, error_messages={"required": "DIV is required (e.g. OL)."})
    bill_no = forms.CharField(max_length=5, error_messages={"required": "Invoice no. is required."})
    bill_date = forms.DateField(
        input_formats=["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"],
        error_messages={"required": "Invoice date is required.", "invalid": "Enter the date as DD-MM-YYYY."},
    )
    party_code = forms.CharField(max_length=4, error_messages={"required": "Select a vendor."})
    net_amount = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=ZERO, max_value=MAX,
        error_messages={
            "required": "Balance amount is required.",
            "invalid": "Enter an amount like 5000.00.",
            "min_value": "Balance amount cannot be negative.",
            "max_value": "Balance amount is too large (maximum 99,999,999.99).",
            "max_decimal_places": "Use at most 2 decimal places.",
        },
    )
    cash_discount = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=ZERO, max_value=MAX, required=False,
        error_messages={
            "invalid": "Enter an amount like 50.00.",
            "min_value": "Cash discount cannot be negative.",
            "max_value": "Cash discount is too large.",
            "max_decimal_places": "Use at most 2 decimal places.",
        },
    )

    def clean_div(self):
        return self.cleaned_data["div"].strip().upper()

    def clean_bill_no(self):
        return self.cleaned_data["bill_no"].strip().upper()

    def clean_party_code(self):
        code = self.cleaned_data["party_code"].strip()
        if not Party.objects.filter(party_code=code, group_code=settings.PARTY_CREDITOR_CODE).exists():
            raise forms.ValidationError("Select a vendor from the Vendor Master.")
        return code

    def clean_net_amount(self):
        value = self.cleaned_data["net_amount"]
        if value == 0:
            # Old rule: an entry with a zero balance is not saved.
            raise forms.ValidationError("Balance amount must be more than 0.")
        return value

    def clean_cash_discount(self):
        return self.cleaned_data.get("cash_discount") or ZERO

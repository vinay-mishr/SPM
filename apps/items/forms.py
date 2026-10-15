from decimal import Decimal

from django import forms

from .models import Item

ZERO = Decimal("0")


class ItemForm(forms.ModelForm):
    """Validates Item Master input. Item code is generated, so it isn't a form field."""

    gst_percent = forms.DecimalField(
        max_digits=5, decimal_places=2, min_value=ZERO, max_value=Decimal("100"), required=False,
        error_messages={
            "min_value": "GST %% cannot be negative.",
            "max_value": "GST %% cannot be more than 100.",
            "invalid": "Enter a valid GST percentage (for example 18 or 18.00).",
        },
    )
    rate = forms.DecimalField(
        max_digits=9, decimal_places=2, min_value=ZERO, required=False,
        error_messages={
            "min_value": "Rate cannot be negative.",
            "max_digits": "Rate cannot be more than 9,999,999.99.",
            "invalid": "Enter a valid rate (for example 4000.00).",
        },
    )
    # Negative opening balances are allowed (the old data has some).
    opening_balance = forms.DecimalField(
        max_digits=9, decimal_places=2, required=False,
        error_messages={
            "max_digits": "Opening balance cannot be more than 9,999,999.99.",
            "invalid": "Enter a valid opening balance.",
        },
    )

    class Meta:
        model = Item
        fields = [
            "item_name_1",
            "item_name_2",
            "item_name_3",
            "unit",
            "hsn_code",
            "gst_percent",
            "rate",
            "opening_balance",
        ]

    def clean_unit(self):
        # Units are stored upper-case (NUM, SET, KG) like the old software.
        return (self.cleaned_data.get("unit") or "").upper()

    def clean(self):
        cleaned = super().clean()
        # Store 0 rather than NULL for empty numbers, as the old software expects.
        for name in ("gst_percent", "rate", "opening_balance"):
            if cleaned.get(name) is None and name not in self.errors:
                cleaned[name] = ZERO
        return cleaned

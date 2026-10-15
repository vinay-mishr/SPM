from django import forms

from apps.parties.services import normalize_mobile


class MarketingManagerForm(forms.Form):
    """Validates a marketing manager. The code is generated, so it is not a field."""

    name = forms.CharField(max_length=25, error_messages={"required": "Manager name is required."})
    address_1 = forms.CharField(max_length=30, required=False)
    address_2 = forms.CharField(max_length=30, required=False)
    mobile = forms.CharField(max_length=20, required=False)

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split()).upper()

    def clean_mobile(self):
        # Same rule as Party Master: 10 digits (+91 / 0 prefixes and spaces are accepted).
        value = self.cleaned_data["mobile"].strip()
        if not value:
            return ""
        digits = normalize_mobile(value)
        if not (digits.isdigit() and len(digits) == 10):
            raise forms.ValidationError("Mobile number must be 10 digits.")
        return digits

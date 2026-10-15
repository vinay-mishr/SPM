from django import forms


class MaterialForm(forms.Form):
    """Validates a material. The code is generated, so it is not a field."""

    name = forms.CharField(max_length=20, error_messages={"required": "Name is required."})

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split()).upper()

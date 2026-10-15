from decimal import Decimal

from django import forms

ZERO = Decimal("0")
PART_TYPE_CHOICES = [("", "—"), ("R", "Raw Material (RM)"), ("C", "Component (CP)"), ("S", "Consumable (CS)")]


class PartForm(forms.Form):
    """Validates a Part Master entry (old VFP form "PART MASTER")."""

    part_number = forms.CharField(max_length=10, error_messages={"required": "Part No. is required."})
    description_1 = forms.CharField(max_length=35, required=False, label="Part Description")
    description_2 = forms.CharField(max_length=35, required=False, label="Part Description 2")
    drawing_no = forms.CharField(max_length=10, required=False)
    gauge = forms.CharField(max_length=10, required=False)
    packing = forms.IntegerField(required=False, min_value=0, error_messages={"invalid": "Packing must be a whole number."})
    grade = forms.CharField(max_length=2, required=False)
    gross_weight = forms.DecimalField(max_digits=10, decimal_places=4, required=False, min_value=ZERO)
    quantity_in_order = forms.DecimalField(max_digits=11, decimal_places=3, required=False, min_value=ZERO)

    purchase_rate = forms.DecimalField(max_digits=10, decimal_places=4, required=False, min_value=ZERO)
    sale_rate = forms.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=ZERO)
    opening_stock = forms.DecimalField(max_digits=12, decimal_places=3, required=False, min_value=ZERO)
    reorder_qty = forms.DecimalField(max_digits=11, decimal_places=3, required=False, min_value=ZERO)
    material = forms.CharField(max_length=15, required=False)
    weight_by_100 = forms.DecimalField(max_digits=7, decimal_places=3, required=False, min_value=ZERO)
    current_stock = forms.DecimalField(max_digits=10, decimal_places=0, required=False, min_value=ZERO)
    location = forms.CharField(max_length=10, required=False)
    unit = forms.CharField(max_length=3, required=False)
    hsn_code = forms.CharField(max_length=8, required=False)
    gst_percent = forms.DecimalField(
        max_digits=5, decimal_places=2, required=False, min_value=ZERO, max_value=Decimal("100"),
        error_messages={"max_value": "GST %% cannot be more than 100."},
    )

    sub_assembly = forms.BooleanField(required=False)
    part_type = forms.ChoiceField(choices=PART_TYPE_CHOICES, required=False)

    supplier_1 = forms.CharField(max_length=4, required=False)
    rate_1 = forms.DecimalField(max_digits=10, decimal_places=4, required=False, min_value=ZERO)
    supplier_2 = forms.CharField(max_length=4, required=False)
    rate_2 = forms.DecimalField(max_digits=10, decimal_places=4, required=False, min_value=ZERO)
    supplier_3 = forms.CharField(max_length=4, required=False)
    rate_3 = forms.DecimalField(max_digits=10, decimal_places=4, required=False, min_value=ZERO)
    supplier_4 = forms.CharField(max_length=4, required=False)
    rate_4 = forms.DecimalField(max_digits=10, decimal_places=4, required=False, min_value=ZERO)

    def clean_part_number(self):
        return self.cleaned_data["part_number"].strip().upper()

    def clean_description_1(self):
        return " ".join(self.cleaned_data["description_1"].split()).upper()

    def clean_unit(self):
        return self.cleaned_data["unit"].strip().upper()

    def clean_material(self):
        return self.cleaned_data["material"].strip().upper()

    def _clean_supplier(self, field):
        from apps.parties.models import Party

        code = self.cleaned_data[field].strip().upper()
        if code and not Party.objects.filter(party_code=code).exists():
            raise forms.ValidationError("Select a party from the Party Master.")
        return code

    def clean_supplier_1(self):
        return self._clean_supplier("supplier_1")

    def clean_supplier_2(self):
        return self._clean_supplier("supplier_2")

    def clean_supplier_3(self):
        return self._clean_supplier("supplier_3")

    def clean_supplier_4(self):
        return self._clean_supplier("supplier_4")

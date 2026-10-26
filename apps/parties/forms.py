import re

from django import forms

from . import services
from .choices import GstCategory, PartyType, SupplyType

YES_NO = [("true", "Yes"), ("false", "No")]
PHONE_CHARS = re.compile(r"^[0-9+\-\s/(),.]*$")


class PartyForm(forms.Form):
    """
    Validates Party Master input (party code is generated, so it isn't a field).

    Existing records from the old software contain free-form values ('.', odd
    GST numbers, several numbers in one phone field). Strict checks therefore only
    apply to values the user actually typed or changed — pass the current record
    as ``original`` (a dict from services.serialize_party) when modifying.
    """

    name = forms.CharField(max_length=40, error_messages={"required": "Party name is required."})
    # Not shown on the Customer Master form: new parties default to Sundry Debtor
    # (see clean()); editing an existing Supplier/Both party here leaves its type as is.
    party_type = forms.ChoiceField(choices=PartyType.choices, required=False)
    address_1 = forms.CharField(max_length=50, required=False)
    address_2 = forms.CharField(max_length=50, required=False)
    address_3 = forms.CharField(max_length=50, required=False)
    city = forms.CharField(max_length=50, required=False)
    pin = forms.CharField(max_length=6, required=False)
    state_code = forms.CharField(max_length=4, required=False)  # gstate.gcode
    mkt_manager = forms.CharField(max_length=2, required=False)  # mm_mst.mcode
    rep_code = forms.CharField(max_length=2, required=False)  # rep_mst.rcode
    gst_no = forms.CharField(max_length=16, required=False)
    gst_category = forms.ChoiceField(choices=GstCategory.choices, required=False)
    contact_person_1 = forms.CharField(max_length=20, required=False)
    mobile_1 = forms.CharField(max_length=20, required=False)
    contact_person_2 = forms.CharField(max_length=20, required=False)
    mobile_2 = forms.CharField(max_length=20, required=False)
    email = forms.CharField(max_length=30, required=False)
    transport = forms.CharField(max_length=25, required=False)
    credit_days = forms.IntegerField(
        min_value=0, max_value=999, required=False,
        error_messages={
            "invalid": "Credit days must be a whole number.",
            "min_value": "Credit days cannot be negative.",
            "max_value": "Credit days cannot be more than 999.",
        },
    )
    is_active = forms.TypedChoiceField(choices=YES_NO, coerce=lambda v: v == "true", initial="true")
    association = forms.CharField(max_length=4, required=False)
    supply_type = forms.ChoiceField(choices=[("", "—")] + list(SupplyType.choices), required=False)
    permit = forms.TypedChoiceField(choices=YES_NO, coerce=lambda v: v == "true", initial="false", required=False)

    def __init__(self, *args, original=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.original = original or {}

    def _changed(self, field, value):
        return value != (self.original.get(field) or "")

    def clean_name(self):
        # The old software keeps names in capitals.
        return self.cleaned_data["name"].strip().upper()

    def clean_pin(self):
        value = self.cleaned_data["pin"].strip()
        if value and self._changed("pin", value) and not re.fullmatch(r"\d{6}", value):
            raise forms.ValidationError("PIN must be exactly 6 digits.")
        return value

    def _clean_mobile(self, field):
        value = self.cleaned_data[field].strip()
        if value and self._changed(field, value):
            if not PHONE_CHARS.match(value):
                raise forms.ValidationError("Use digits, spaces, + or - only.")
            digits = services.normalize_mobile(value)
            if not (digits.isdigit() and len(digits) == 10):
                raise forms.ValidationError("Mobile number must be 10 digits.")
            return digits
        return value

    def clean_mobile_1(self):
        return self._clean_mobile("mobile_1")

    def clean_mobile_2(self):
        return self._clean_mobile("mobile_2")

    def clean_email(self):
        value = self.cleaned_data["email"].strip()
        if value and self._changed("email", value):
            try:
                forms.EmailField().clean(value)
            except forms.ValidationError:
                raise forms.ValidationError("Enter a valid email address (e.g. name@company.com).")
            value = value.lower()
        return value

    def clean_gst_no(self):
        value = self.cleaned_data["gst_no"].replace(" ", "").upper()
        if value and self._changed("gst_no", value):
            error = services.gstin_error(value)
            if error:
                raise forms.ValidationError(error)
        return value

    def clean_state_code(self):
        value = self.cleaned_data["state_code"].strip()
        if value and value not in services.states_by_gcode() and self._changed("state_code", value):
            raise forms.ValidationError("Select a state from the list.")
        return value

    def clean_mkt_manager(self):
        value = self.cleaned_data["mkt_manager"].strip()
        if value and value not in dict(services.mkt_managers()) and self._changed("mkt_manager", value):
            raise forms.ValidationError("Select a market manager from the list.")
        return value

    def clean_rep_code(self):
        value = self.cleaned_data["rep_code"].strip()
        if value and value not in dict(services.reps()) and self._changed("rep_code", value):
            raise forms.ValidationError("Select a rep from the list.")
        return value

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("party_type"):
            cleaned["party_type"] = self.original.get("party_type") or PartyType.DEBTOR
        gst_no = cleaned.get("gst_no") or ""
        state_code = cleaned.get("state_code") or ""
        checks_needed = self._changed("gst_no", gst_no) or self._changed("state_code", state_code)
        if gst_no and "gst_no" not in self.errors and checks_needed:
            state = services.states_by_gcode().get(state_code)
            if not state_code:
                # Fill the state from the GSTIN when none was picked.
                cleaned["state_code"] = services.gcode_for_gst_state(gst_no[:2]) or ""
            elif state and gst_no[:2] != state["gst_code"]:
                self.add_error(
                    "gst_no",
                    f"GST no. starts with {gst_no[:2]}, but the selected state's code is {state['gst_code']}.",
                )
        return cleaned

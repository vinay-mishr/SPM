"""GST Master logic (old software's ``gst`` table). Old VFP form: GST MASTER."""
from decimal import Decimal, InvalidOperation

from django.conf import settings

from apps.gl.models import Ledger

from .models import GstRate

PERMISSION = "gst.change_gst_master"

ACCOUNT_FIELDS = [
    "sale_taxfree_account", "sale_account", "sale_cgst_account", "sale_sgst_account",
    "sale_interstate_account", "sale_igst_account",
    "purchase_taxfree_account", "purchase_account", "purchase_cgst_account", "purchase_sgst_account",
    "purchase_interstate_account", "purchase_igst_account",
]

# Labels used in validation messages, matching the on-screen field names.
ACCOUNT_LABELS = {
    "sale_taxfree_account": "Sale Taxfree A/C",
    "sale_account": "Sale A/C",
    "sale_cgst_account": "Sale CGST A/C",
    "sale_sgst_account": "Sale SGST A/C",
    "sale_interstate_account": "Sale A/C (interstate)",
    "sale_igst_account": "Sale IGST A/C",
    "purchase_taxfree_account": "Purchase Taxfree A/C",
    "purchase_account": "Purchase A/C",
    "purchase_cgst_account": "Purchase CGST A/C",
    "purchase_sgst_account": "Purchase SGST A/C",
    "purchase_interstate_account": "Purchase A/C (interstate)",
    "purchase_igst_account": "Purchase IGST A/C",
}


class GstError(Exception):
    """A save that must be refused, with a message for the user."""

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise GstError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _db():
    return GstRate.objects.db


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def serialize(rate):
    data = {"rate": f"{rate.rate:.2f}"}
    for field in ACCOUNT_FIELDS:
        data[field] = _clean(getattr(rate, field))
    return data


def list_rates():
    return [serialize(r) for r in GstRate.objects.order_by("rate")]


def get_rate(raw_rate):
    """The GstRate for this GST %, or ``None`` if not defined. Raises ``GstError`` if
    ``raw_rate`` itself isn't a usable number."""
    value = parse_rate(raw_rate)
    return GstRate.objects.filter(rate=value).first()


def parse_rate(raw):
    text = str(raw if raw is not None else "").strip().replace("%", "")
    if text == "":
        raise GstError("GST % is required.", {"rate": "GST % is required."})
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise GstError("Enter a valid GST % (for example 18 or 5.00).", {"rate": "Enter a valid number."})
    if not value.is_finite() or value < 0:
        raise GstError("GST % must be zero or more.", {"rate": "GST % must be zero or more."})
    if value >= Decimal("1000"):
        raise GstError("GST % is too large.", {"rate": "GST % is too large."})
    return value.quantize(Decimal("0.01"))


def _clean_accounts(payload):
    codes = set()
    for field in ACCOUNT_FIELDS:
        code = str((payload or {}).get(field, "") or "").strip().upper()
        if code:
            codes.add(code)
    known = set(Ledger.objects.filter(pk__in=codes).values_list("ledger_code", flat=True))

    cleaned = {}
    errors = {}
    for field in ACCOUNT_FIELDS:
        code = str((payload or {}).get(field, "") or "").strip().upper()
        if code and code not in known:
            errors[field] = f"{ACCOUNT_LABELS[field]}: ledger account {code} was not found."
            continue
        cleaned[field] = code
    if errors:
        raise GstError("Some account fields are not valid.", errors)
    return cleaned


def create(raw_rate, payload, username=""):
    """CONFIRM in ADD mode: the GST % must not already be defined."""
    _require_writes()
    rate = parse_rate(raw_rate)
    if GstRate.objects.filter(rate=rate).exists():
        raise GstError("GST Rate Already Defined...", {"rate": "GST Rate Already Defined..."})
    cleaned = _clean_accounts(payload)
    obj = GstRate(rate=rate, **cleaned)
    obj.save(force_insert=True)
    return obj


def update(raw_rate, payload):
    """CONFIRM in MODIFY mode: the GST % must already be defined."""
    _require_writes()
    rate = parse_rate(raw_rate)
    obj = GstRate.objects.filter(rate=rate).first()
    if obj is None:
        raise GstError("GST Rate Not Defined...", {"rate": "GST Rate Not Defined..."})
    cleaned = _clean_accounts(payload)
    for field, value in cleaned.items():
        setattr(obj, field, value)
    obj.save()
    return obj


def delete(raw_rate):
    _require_writes()
    rate = parse_rate(raw_rate)
    deleted, _ = GstRate.objects.filter(rate=rate).delete()
    if not deleted:
        raise GstError("This GST rate does not exist.")

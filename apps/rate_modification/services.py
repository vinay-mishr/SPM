"""
Rate Modification (old VFP form ``itemrate1``) — bulk-edit the purchase rate,
opening/current stock, GST% and location of parts. No new table: this is a
service layer over apps.parts.models.Part (the existing part-mst). Only these
five columns are ever written; every other field (name, HSN, suppliers, ...)
is left exactly as it is, so Item Master and Part Master keep working on the
same records unaffected.
"""
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction

from apps.parts.models import Part
from apps.parts.services import duplicate_part_numbers

PERMISSION = "parts.change_rate"
ZERO = Decimal("0.00")
MAX_RATE = Decimal("999999.9999")  # part-mst.rate is decimal(10, 4)


class RateModificationError(Exception):
    """Validation problem; ``errors`` maps part number -> message."""

    def __init__(self, errors):
        super().__init__("Some rates are not valid.")
        self.errors = errors


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _clean(value):
    return (value or "").strip()


def _money(value):
    return f"{(value or 0):.2f}"


def rows():
    """Every part, sorted by code (as the old grid: CODE ascending)."""
    result = []
    parts = Part.objects.order_by("part_number").values_list(
        "part_number", "description_1", "purchase_rate", "opening_stock", "current_stock", "gst_percent", "location"
    )
    for part_number, name, rate, op_stk, cur_stk, gst, location in parts:
        result.append({
            "id": part_number,
            "code": _clean(part_number),
            "name": _clean(name),
            "rate": _money(rate),
            "opening_stock": _money(op_stk),
            "current_stock": _money(cur_stk),
            "gst_percent": _money(gst),
            "location": _clean(location),
        })
    return result


def parse_rate(raw):
    """'1500.5' -> Decimal('1500.5000'); blank -> error (see save())."""
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if text == "":
        raise ValueError("Enter the new rate.")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("Enter a number (for example 1500.00).")
    if not value.is_finite():
        raise ValueError("Enter a number (for example 1500.00).")
    if value < 0:
        raise ValueError("Rate cannot be negative.")
    if value > MAX_RATE:
        raise ValueError("Rate is too large (maximum 999999.9999).")
    return value.quantize(Decimal("0.0001"))


def parse_decimal(raw, decimal_places, label, max_value=None):
    """Generic non-negative decimal parser for the stock/GST% fields."""
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if text == "":
        raise ValueError(f"Enter the {label.lower()}.")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Enter a number for {label.lower()}.")
    if not value.is_finite():
        raise ValueError(f"Enter a number for {label.lower()}.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    if max_value is not None and value > max_value:
        raise ValueError(f"{label} cannot be more than {max_value}.")
    return value.quantize(Decimal(1).scaleb(-decimal_places))


def parse_location(raw):
    text = str(raw if raw is not None else "").strip().upper()
    if len(text) > 10:
        raise ValueError("Location cannot be more than 10 characters.")
    return text


# payload key -> (Part model field, parser)
FIELD_PARSERS = {
    "rate": ("purchase_rate", parse_rate),
    "opening_stock": ("opening_stock", lambda raw: parse_decimal(raw, 3, "Opening stock")),
    "current_stock": ("current_stock", lambda raw: parse_decimal(raw, 0, "Current stock")),
    "gst_percent": ("gst_percent", lambda raw: parse_decimal(raw, 2, "GST %", max_value=Decimal("100"))),
    "location": ("location", parse_location),
}


def save(changes, username=""):
    """
    Save changed rows: [{"code": ..., "rate": ..., "opening_stock": ..., ...}, ...].
    Only the keys present in each change are validated and written -- a change
    that only sends "rate" leaves opening_stock/current_stock/gst_percent/location
    untouched, and vice versa. Every row is validated first; then all are written
    in one transaction (all or nothing). Returns the number of parts updated.
    """
    if not isinstance(changes, list) or not changes:
        raise RateModificationError({"": "No changes to save."})

    errors, updates = {}, {}
    duplicates = duplicate_part_numbers()
    for change in changes:
        change = change or {}
        code = str(change.get("code", "")).strip()
        if not code:
            continue
        if code in duplicates:
            errors[code] = "This part number exists more than once in the old data; it cannot be changed here."
            continue
        row_updates = {}
        for key, (db_field, parser) in FIELD_PARSERS.items():
            if key not in change:
                continue
            try:
                row_updates[db_field] = parser(change[key])
            except ValueError as exc:
                errors[code] = str(exc)
                row_updates = None
                break
        if row_updates:
            updates[code] = row_updates

    existing = set(Part.objects.filter(part_number__in=list(updates)).values_list("part_number", flat=True))
    for code in list(updates):
        if code not in existing:
            errors[code] = "Part not found."
            del updates[code]
    if errors:
        raise RateModificationError(errors)

    with transaction.atomic(using=Part.objects.db):
        for code, fields in updates.items():
            Part.objects.filter(part_number=code).update(**fields)
    return len(updates)

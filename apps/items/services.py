"""Item Master business logic. Views stay thin and call these functions."""
from django.conf import settings
from django.db import transaction
from django.db.models import ProtectedError

from config.legacy import fill_blank_columns, tables_using

from .models import Item

CODE_WIDTH = 4


class ItemInUseError(Exception):
    """Raised when an item can't be deleted because other records reference it."""


class ItemWriteDisabledError(Exception):
    """Raised when writing to the old software's database hasn't been enabled yet."""


class ItemCodeConflictError(Exception):
    """Raised when the generated code was taken by someone else in the meantime."""


def writes_enabled():
    """Writes are always allowed locally; on the legacy SQL Server only once enabled."""
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise ItemWriteDisabledError(
            "Item Master is read-only for now: saving to the SP_MACHINE database has not been enabled yet."
        )


def next_item_code():
    """Next sequential code: one more than the highest numeric code, zero-padded (0001, 0002, ...)."""
    codes = Item.objects.values_list("item_code", flat=True)
    numbers = [int(code) for code in codes if code and code.strip().isdigit()]
    return str(max(numbers, default=0) + 1).zfill(CODE_WIDTH)


def create_item(form, username=""):
    """Save a new item from a valid ItemForm, assigning the next item code."""
    _require_writes()
    db = Item.objects.db
    with transaction.atomic(using=db):
        item = form.save(commit=False)
        item.item_code = next_item_code()
        # The table has no key constraint, so never overwrite an existing code.
        if Item.objects.filter(item_code=item.item_code).exists():
            raise ItemCodeConflictError(f"Item code {item.item_code} already exists. Please try again.")
        item.save(force_insert=True)
        fill_blank_columns(db, Item._meta.db_table, "i_code", item.item_code, username)
    return item


def update_item(form):
    """Save changes to an existing item. The item code never changes."""
    _require_writes()
    return form.save()


def delete_item(item):
    """Delete an item unless other records still reference it."""
    _require_writes()
    used_in = tables_using(Item.objects.db, settings.ITEM_USAGE_TABLES, item.item_code)
    if used_in:
        raise ItemInUseError(
            f"Item {item.item_code} cannot be deleted because it is used in: {', '.join(used_in)}."
        )
    try:
        item.delete()
    except ProtectedError as exc:
        used_in = sorted({obj._meta.verbose_name_plural for obj in exc.protected_objects})
        raise ItemInUseError(
            f"Item {item.item_code} cannot be deleted because it is used in: {', '.join(used_in)}."
        ) from exc


def _decimal(value):
    return str(value) if value is not None else "0.00"


def serialize_item(item):
    return {
        "id": item.item_code,
        "item_code": item.item_code,
        "item_name_1": item.item_name_1 or "",
        "item_name_2": item.item_name_2 or "",
        "item_name_3": item.item_name_3 or "",
        "unit": item.unit or "",
        "hsn_code": item.hsn_code or "",
        "gst_percent": _decimal(item.gst_percent),
        "rate": _decimal(item.rate),
        "opening_balance": _decimal(item.opening_balance),
    }


def list_items():
    """All items, sorted by item code (as the old list: SET ORDER TO i_code)."""
    return [serialize_item(item) for item in Item.objects.order_by("item_code")]

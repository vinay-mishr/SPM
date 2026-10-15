"""Marketing Manager logic (old software's mm_mst). Views stay thin and call these."""
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from config.legacy import fill_blank_columns, tables_using, values_in_use

from .models import MarketingManager

CODE_WIDTH = 2
# Where a manager code is used: parties (Party Master MKT MANAGER) and orders.
USAGE_TABLES = [("cust_mst", "cmm"), ("ord_mst", "mcode"), ("ord_mst1", "mcode"), ("order1", "mcode")]


class ManagerError(Exception):
    """A save / delete that must be refused, with a message for the user."""


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _db():
    return MarketingManager.objects.db


def _forget_party_lookup():
    # Party Master caches the manager list for its MKT MANAGER dropdown.
    cache.delete(f"parties:mm:{_db()}")


def next_code():
    """One more than the highest numeric code, 2 digits (01 ... 99), like the old software."""
    # Also skip codes that old bills / parties / orders still refer to, so a new entry
    # never "inherits" someone else's history.
    codes = set(MarketingManager.objects.values_list("code", flat=True)) | values_in_use(_db(), USAGE_TABLES)
    numbers = [int(c) for c in codes if c and c.strip().isdigit()]
    number = max(numbers, default=0) + 1
    if number >= 10 ** CODE_WIDTH:
        raise ManagerError("No free manager code left (01-99 are all used).")
    return str(number).zfill(CODE_WIDTH)


def _clean(value):
    return (value or "").strip()


def serialize(manager):
    return {
        "id": manager.code,
        "code": _clean(manager.code),
        "name": _clean(manager.name),
        "address_1": _clean(manager.address_1),
        "address_2": _clean(manager.address_2),
        "city": _clean(manager.city),
        "mobile": _clean(manager.mobile),
        "phone": _clean(manager.phone),
    }


def list_managers():
    return [serialize(m) for m in MarketingManager.objects.order_by("name")]


def _duplicate_name(name, exclude_code=None):
    qs = MarketingManager.objects.filter(name__iexact=name)
    if exclude_code:
        qs = qs.exclude(code=exclude_code)
    return qs.exists()


def create(data, username=""):
    if _duplicate_name(data["name"]):
        raise ManagerError(f"A manager named {data['name']} already exists.")
    with transaction.atomic(using=_db()):
        manager = MarketingManager(code=next_code(), **data)
        manager.save(force_insert=True)
        fill_blank_columns(_db(), "mm_mst", "mcode", manager.code, username)
    _forget_party_lookup()
    return manager


def update(manager, data):
    if _duplicate_name(data["name"], exclude_code=manager.code):
        raise ManagerError(f"A manager named {data['name']} already exists.")
    for field, value in data.items():
        setattr(manager, field, value)
    manager.save(force_update=True)
    _forget_party_lookup()
    return manager


def delete(manager):
    used_in = tables_using(_db(), USAGE_TABLES, manager.code)
    if used_in:
        raise ManagerError(
            f"Manager {manager.code} ({_clean(manager.name)}) cannot be deleted because it is used in: "
            f"{', '.join(used_in)}."
        )
    manager.delete()
    _forget_party_lookup()

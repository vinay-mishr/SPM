"""Rep Master logic (old software's rep_mst). Views stay thin and call these."""
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from config.legacy import fill_blank_columns, tables_using

from .models import Rep

CODE_WIDTH = 2
# Where a rep code is used: parties, bills, challans and orders (checked on delete).
USAGE_TABLES = [
    ("cust_mst", "crep"), ("bill", "rep_cod"), ("t_bill", "rep_cod"), ("c_bill", "rep_cod"),
    ("chl_mst", "rep_code"), ("order1", "rep_code"),
]


class RepError(Exception):
    """A save / delete that must be refused, with a message for the user."""


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _db():
    return Rep.objects.db


def _forget_party_lookup():
    # Party Master caches the rep list for its REP CODE dropdown.
    cache.delete(f"parties:rep:{_db()}")


def next_code():
    """One more than the highest numeric code currently in the Rep table, 2 digits."""
    codes = Rep.objects.values_list("code", flat=True)
    numbers = [int(c) for c in codes if c and c.strip().isdigit()]
    number = max(numbers, default=0) + 1
    if number >= 10 ** CODE_WIDTH:
        raise RepError("No free rep code left (up to 99 are used).")
    return str(number).zfill(CODE_WIDTH)


def _clean(value):
    return (value or "").strip()


def serialize(rep):
    return {
        "id": rep.code,
        "code": _clean(rep.code),
        "name": _clean(rep.name),
        "father_name": _clean(rep.father_name),
        "address_1": _clean(rep.address_1),
        "address_2": _clean(rep.address_2),
        "address_3": _clean(rep.address_3),
        "permanent_location": _clean(rep.permanent_location),
        "city": _clean(rep.address_3),  # the grid's CITY column (last address line)
        "phone": _clean(rep.phone),
        "mobile": _clean(rep.mobile),
    }


def list_reps():
    return [serialize(r) for r in Rep.objects.order_by("name")]


def _duplicate_name(name, exclude_code=None):
    qs = Rep.objects.filter(name__iexact=name)
    if exclude_code:
        qs = qs.exclude(code=exclude_code)
    return qs.exists()


def create(data, username=""):
    if _duplicate_name(data["name"]):
        raise RepError(f"A rep named {data['name']} already exists.")
    with transaction.atomic(using=_db()):
        rep = Rep(code=next_code(), **data)
        rep.save(force_insert=True)
        fill_blank_columns(_db(), "rep_mst", "rcode", rep.code, username)
    _forget_party_lookup()
    return rep


def update(rep, data):
    if _duplicate_name(data["name"], exclude_code=rep.code):
        raise RepError(f"A rep named {data['name']} already exists.")
    for field, value in data.items():
        setattr(rep, field, value)
    rep.save(force_update=True)
    _forget_party_lookup()
    return rep


def delete(rep):
    used_in = tables_using(_db(), USAGE_TABLES, rep.code)
    if used_in:
        raise RepError(
            f"Rep {rep.code} ({_clean(rep.name)}) is already being used and cannot be deleted "
            f"(found in: {', '.join(used_in)})."
        )
    rep.delete()
    _forget_party_lookup()

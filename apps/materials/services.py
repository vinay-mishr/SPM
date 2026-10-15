"""Material Master logic (old software's mat_mst). Views stay thin and call these."""
from django.conf import settings
from django.db import transaction

from config.legacy import fill_blank_columns, values_in_use

from .models import Material

# No other table in SP_MACHINE references a material by this code (see models.py).
USAGE_TABLES = []


class MaterialError(Exception):
    """A save / delete that must be refused, with a message for the user."""


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _db():
    return Material.objects.db


def next_code(name):
    """
    Old software's rule (same as Party Master / Supervisor Master): first
    character of the name + the next 3-digit number for that character, e.g.
    the next 'A' material after A001 is A002.
    """
    first = (name or "").strip()[:1].upper()
    letter = first if first.isalnum() else "0"
    codes = set(Material.objects.filter(code__startswith=letter).values_list("code", flat=True))
    codes |= {c for c in values_in_use(_db(), USAGE_TABLES) if c.startswith(letter)}
    numbers = [int(c[1:]) for c in codes if len(c) == 4 and c[1:].isdigit()]
    number = max(numbers, default=0) + 1
    if number > 999:
        raise MaterialError(f"No free material code left for '{letter}' (all {letter}001-{letter}999 are used).")
    return f"{letter}{number:03d}"


def _clean(value):
    return (value or "").strip()


def serialize(material):
    return {"id": material.code, "code": _clean(material.code), "name": _clean(material.name)}


def list_materials():
    return [serialize(m) for m in Material.objects.order_by("name")]


def _duplicate_name(name, exclude_code=None):
    qs = Material.objects.filter(name__iexact=name)
    if exclude_code:
        qs = qs.exclude(code=exclude_code)
    return qs.exists()


def create(data, username=""):
    if _duplicate_name(data["name"]):
        raise MaterialError(f"A material named {data['name']} already exists.")
    with transaction.atomic(using=_db()):
        material = Material(code=next_code(data["name"]), name=data["name"])
        material.save(force_insert=True)
        fill_blank_columns(_db(), "mat_mst", "code", material.code, username)
    return material


def update(material, data):
    if _duplicate_name(data["name"], exclude_code=material.code):
        raise MaterialError(f"A material named {data['name']} already exists.")
    material.name = data["name"]
    material.save(force_update=True)
    return material


def delete(material):
    used_in = values_in_use(_db(), USAGE_TABLES)  # empty for now; see USAGE_TABLES note
    if material.code in used_in:
        raise MaterialError(
            f"Material {material.code} ({_clean(material.name)}) is already used in existing "
            "transactions and cannot be deleted."
        )
    material.delete()

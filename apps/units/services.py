"""Unit Master logic (old software's unit table)."""
from django.conf import settings

from config.legacy import fill_blank_columns, tables_using

from .models import Unit

PERMISSION = "units.change_unit_master"

# Tables whose "unit"/"uom" column stores a value from this list, checked before delete.
USAGE_TABLES = [
    ("item", "unit"), ("part-mst", "uom"), ("ms", "uom"), ("order", "uom"),
    ("se", "uom"), ("sec", "uom"), ("sep", "uom"), ("ser", "uom"),
    ("vs", "uom"), ("vsc", "uom"), ("vsp", "uom"), ("vsr", "uom"),
]


class UnitError(Exception):
    """A save / delete that must be refused, with a message for the user."""

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise UnitError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _db():
    return Unit.objects.db


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def serialize(unit):
    return {"id": unit.name, "name": _clean(unit.name)}


def list_units():
    return [serialize(u) for u in Unit.objects.order_by("name")]


def _clean_name(raw):
    value = (raw or "").strip().upper()
    if not value:
        raise UnitError("Unit is required.", {"name": "Unit is required."})
    if len(value) > 3:
        raise UnitError("Unit must be at most 3 characters.", {"name": "Unit must be at most 3 characters."})
    return value


def create(raw_name, username=""):
    _require_writes()
    name = _clean_name(raw_name)
    if Unit.objects.filter(pk=name).exists():
        raise UnitError(f"Unit {name} already exists.", {"name": f"Unit {name} already exists."})
    unit = Unit(name=name)
    unit.save(force_insert=True)
    fill_blank_columns(_db(), Unit._meta.db_table, "name", name, username)
    return unit


def update(unit, raw_name):
    _require_writes()
    name = _clean_name(raw_name)
    if name != unit.name and Unit.objects.filter(pk=name).exists():
        raise UnitError(f"Unit {name} already exists.", {"name": f"Unit {name} already exists."})
    if name != unit.name:
        # The real table has no foreign key, but rename in place rather than
        # insert+delete so a concurrent read never sees the unit disappear.
        old_name = unit.name
        Unit.objects.filter(pk=old_name).update(name=name)
        unit.name = name
    return unit


def delete(unit):
    _require_writes()
    used_in = tables_using(_db(), USAGE_TABLES, unit.name)
    if used_in:
        raise UnitError(f"Unit {unit.name} cannot be deleted because it is used in: {', '.join(used_in)}.")
    unit.delete()

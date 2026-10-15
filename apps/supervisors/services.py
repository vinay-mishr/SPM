"""Supervisor Master logic (old software's sup_mst). Views stay thin and call these."""
from django.conf import settings
from django.db import transaction

from config.legacy import fill_blank_columns, values_in_use

from .models import Supervisor

# No other table in SP_MACHINE was found to reference a supervisor by code
# (checked across every short text column). Kept here so a real reference,
# if one turns up later, only needs adding to this list.
USAGE_TABLES = []


class SupervisorError(Exception):
    """A save / delete that must be refused, with a message for the user."""


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _db():
    return Supervisor.objects.db


def next_code(name):
    """
    Old software's rule (same as Party Master): first letter of the name + the next
    3-digit number for that letter, e.g. the next 'G' supervisor after G001 is G002.
    """
    first = (name or "").strip()[:1].upper()
    letter = first if first.isalnum() else "0"
    codes = set(Supervisor.objects.filter(code__startswith=letter).values_list("code", flat=True))
    codes |= {c for c in values_in_use(_db(), USAGE_TABLES) if c.startswith(letter)}
    numbers = [int(c[1:]) for c in codes if len(c) == 4 and c[1:].isdigit()]
    number = max(numbers, default=0) + 1
    if number > 999:
        raise SupervisorError(f"No free supervisor code left for '{letter}' (all {letter}001-{letter}999 are used).")
    return f"{letter}{number:03d}"


def _clean(value):
    return (value or "").strip()


def serialize(supervisor):
    return {"id": supervisor.code, "code": _clean(supervisor.code), "name": _clean(supervisor.name)}


def list_supervisors():
    return [serialize(s) for s in Supervisor.objects.order_by("name")]


def _duplicate_name(name, exclude_code=None):
    qs = Supervisor.objects.filter(name__iexact=name)
    if exclude_code:
        qs = qs.exclude(code=exclude_code)
    return qs.exists()


def create(data, username=""):
    if _duplicate_name(data["name"]):
        raise SupervisorError(f"A supervisor named {data['name']} already exists.")
    with transaction.atomic(using=_db()):
        supervisor = Supervisor(code=next_code(data["name"]), name=data["name"])
        supervisor.save(force_insert=True)
        fill_blank_columns(_db(), "sup_mst", "code", supervisor.code, username)
    return supervisor


def update(supervisor, data):
    if _duplicate_name(data["name"], exclude_code=supervisor.code):
        raise SupervisorError(f"A supervisor named {data['name']} already exists.")
    supervisor.name = data["name"]
    supervisor.save(force_update=True)
    return supervisor


def delete(supervisor):
    used_in = values_in_use(_db(), USAGE_TABLES)  # empty for now; see USAGE_TABLES note
    if supervisor.code in used_in:
        raise SupervisorError(f"Supervisor {supervisor.code} ({_clean(supervisor.name)}) is already being used.")
    supervisor.delete()

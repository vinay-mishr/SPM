"""General Ledger Master logic (old software's gled_mst table)."""
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import connections, transaction

from config.legacy import fill_blank_columns, tables_using

from .models import Ledger

PERMISSION = "gl.change_general_ledger"

# History / transaction tables that reference a ledger code (gcode), checked before delete.
USAGE_TABLES = [
    ("adj", "gcode"), ("b_debt", "gcode"), ("cr_out", "gcode"), ("crhis", "gcode"),
    ("mis_mst", "gcode"), ("pur_mst", "gcode"), ("pur_mst1", "gcode"), ("pur_mst2", "gcode"),
    ("rmis_mst", "gcode"), ("she", "gcode"), ("trial", "gcode"),
    ("gledhis", "gcode"), ("gledmst1", "gcode"), ("gledmst2", "gcode"),
    ("gledmst3", "gcode"), ("tgledmst", "gcode"),
]


class LedgerError(Exception):
    """A save / delete that must be refused, with a message for the user."""

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _require_writes():
    if not writes_enabled():
        raise LedgerError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def _db():
    return Ledger.objects.db


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def groups():
    """[{code, name}] from grp_mst, sorted by name."""
    with connections[_db()].cursor() as cursor:
        cursor.execute("SELECT [gr_code], [gr_name] FROM [grp_mst] ORDER BY [gr_name]")
        rows = cursor.fetchall()
    return [{"code": str(int(c)), "name": (n or "").strip()} for c, n in rows]


def groups_by_code():
    return {g["code"]: g for g in groups()}


def tree_groups():
    """[{code, name, level}] from group1 (VFP tree help), in code order: a parent sorts before its children."""
    with connections[_db()].cursor() as cursor:
        cursor.execute("SELECT [grp_code], [grp_name] FROM [group1] ORDER BY [grp_code]")
        rows = cursor.fetchall()
    result = []
    for c, n in rows:
        code = (c or "").strip()
        if code:
            result.append({"code": code, "name": (n or "").strip(), "level": (len(code) - 1) // 2})
    return result


def next_ledger_code(description):
    """Old rule: first letter of the description + the next 3-digit number for that letter."""
    first = (description or "").strip()[:1].upper()
    letter = first if first.isalnum() else "0"
    codes = Ledger.objects.filter(ledger_code__startswith=letter).values_list("ledger_code", flat=True)
    numbers = [int(c[1:]) for c in codes if c and len(c) == 4 and c[1:].isdigit()]
    number = max(numbers, default=0) + 1
    if number > 999:
        raise LedgerError(f"No free ledger code left for '{letter}' (all {letter}001-{letter}999 are used).")
    return f"{letter}{number:03d}"


def serialize(ledger):
    return {
        "id": ledger.ledger_code,
        "ledger_code": ledger.ledger_code,
        "description": _clean(ledger.description),
        "opening_balance": f"{(ledger.opening_balance or 0):.2f}",
        "group_code": str(int(ledger.group_code)) if ledger.group_code is not None else "",
        "group_name": _clean(ledger.group_name),
        "gl_type": _clean(ledger.gl_type) or "",
    }


def list_ledgers():
    """All ledgers sorted by description (as the old grid)."""
    return [serialize(l) for l in Ledger.objects.order_by("description")]


def parse_opening_balance(raw):
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if text == "":
        return Decimal("0.00")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("Enter an amount like 5000.00.")
    if not value.is_finite():
        raise ValueError("Enter an amount like 5000.00.")
    return value.quantize(Decimal("0.01"))


def _validate(data, original=None):
    original = original or {}
    errors = {}
    description = (data.get("description") or "").strip().upper()
    if not description:
        errors["description"] = "Description is required."

    gl_type = (data.get("gl_type") or "").strip()
    if gl_type and gl_type not in {g["code"] for g in tree_groups()} and gl_type != (original.get("gl_type") or ""):
        errors["gl_type"] = "Select a group from the list."

    group_code = (data.get("group_code") or "").strip()
    if not group_code:
        errors["group_code"] = "Select a ledger group."
    elif group_code not in groups_by_code() and group_code != (original.get("group_code") or ""):
        errors["group_code"] = "Select a ledger group from the list."

    try:
        opening_balance = parse_opening_balance(data.get("opening_balance"))
    except ValueError as exc:
        errors["opening_balance"] = str(exc)
        opening_balance = Decimal("0.00")

    if errors:
        raise LedgerError("Some fields are not valid.", errors)
    return {"description": description, "gl_type": gl_type, "group_code": group_code, "opening_balance": opening_balance}


def create(data, username=""):
    _require_writes()
    cleaned = _validate(data)
    db = _db()
    with transaction.atomic(using=db):
        ledger = Ledger(
            description=cleaned["description"],
            opening_balance=cleaned["opening_balance"],
            group_code=Decimal(cleaned["group_code"]),
            group_name=groups_by_code().get(cleaned["group_code"], {}).get("name", ""),
            gl_type=cleaned["gl_type"] or None,
            uname=(username or "")[:10],
        )
        ledger.ledger_code = next_ledger_code(cleaned["description"])
        if Ledger.objects.filter(ledger_code=ledger.ledger_code).exists():
            raise LedgerError(f"Ledger code {ledger.ledger_code} already exists. Please try again.")
        ledger.save(force_insert=True)
        fill_blank_columns(db, Ledger._meta.db_table, "gcode", ledger.ledger_code, username)
    return ledger


def update(ledger, data):
    _require_writes()
    original = serialize(ledger)
    cleaned = _validate(data, original=original)
    ledger.description = cleaned["description"]
    ledger.opening_balance = cleaned["opening_balance"]
    ledger.gl_type = cleaned["gl_type"] or None
    if cleaned["group_code"] in groups_by_code():
        ledger.group_code = Decimal(cleaned["group_code"])
        ledger.group_name = groups_by_code()[cleaned["group_code"]]["name"]
    ledger.save(force_update=True)
    return ledger


def delete(ledger):
    _require_writes()
    used_in = tables_using(_db(), USAGE_TABLES, ledger.ledger_code)
    if used_in:
        raise LedgerError(
            f"Ledger {ledger.ledger_code} cannot be deleted because it is used in: {', '.join(used_in)}."
        )
    ledger.delete()

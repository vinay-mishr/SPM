"""Helpers for writing to the old software's SQL Server tables (SP_MACHINE)."""
from django.db import connections

TEXT_TYPES = {"char", "varchar", "nchar", "nvarchar", "text", "ntext"}
NUMBER_TYPES = {"decimal", "numeric", "int", "smallint", "tinyint", "bigint", "float", "real", "money"}


def fill_blank_columns(using, table, key_column, key_value, uname="", extra_keys=None):
    """
    After inserting a row through Django, set every column Django didn't fill
    (still NULL) to '' or 0, as the old VFP software expects, and record who
    added it in ``uname`` when that column exists. Only touches this one row.
    """
    connection = connections[using]
    if connection.vendor != "microsoft":
        return  # local SQLite (tests): nothing to do
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = %s", [table]
        )
        columns = cursor.fetchall()
        sets, params = [], []
        for name, data_type in columns:
            if name == "uname" and uname:
                sets.append("[uname] = %s")
                params.append(uname[:10])
            elif data_type in TEXT_TYPES:
                sets.append(f"[{name}] = COALESCE([{name}], '')")
            elif data_type in NUMBER_TYPES:
                sets.append(f"[{name}] = COALESCE([{name}], 0)")
        if sets:
            keys = {key_column: key_value, **(extra_keys or {})}
            where = " AND ".join(f"[{column}] = %s" for column in keys)
            cursor.execute(
                f"UPDATE [{table}] SET {', '.join(sets)} WHERE {where}", params + list(keys.values())
            )


def tables_using(using, checks, value):
    """
    Return the names of tables (from ``checks``: [(table, column), ...]) that
    contain ``value`` in that column. Missing tables are skipped.
    """
    connection = connections[using]
    found = []
    with connection.cursor() as cursor:
        for table, column in checks:
            try:
                cursor.execute(f"SELECT TOP 1 1 FROM [{table}] WHERE [{column}] = %s", [value])
            except Exception:  # table not present in this database
                continue
            if cursor.fetchone():
                found.append(table)
    return found


def values_in_use(using, checks):
    """
    Distinct non-blank values of the given (table, column) pairs — e.g. all rep codes
    that old bills / parties still refer to. Missing tables are skipped.
    """
    connection = connections[using]
    found = set()
    with connection.cursor() as cursor:
        for table, column in checks:
            try:
                cursor.execute(f"SELECT DISTINCT [{column}] FROM [{table}]")
            except Exception:  # table not present in this database
                continue
            found.update((row[0] or "").strip() for row in cursor.fetchall())
    found.discard("")
    return found

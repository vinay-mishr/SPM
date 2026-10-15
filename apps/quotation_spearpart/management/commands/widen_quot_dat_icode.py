"""
Widen ``quot_dat.i_code`` from VARCHAR(4) to VARCHAR(10) in the SQL Server (SP_MACHINE)
database, so a real spare-part number (confirmed up to 10 characters, e.g.
"ABM01_001A") can be saved there without being silently truncated.

This is the ONE schema change the Quotation (Spare Part) module needs: ``quot_dat`` is
otherwise reused as-is (see apps.quotation_spearpart.models for the full picture).
VARCHAR(4) -> VARCHAR(10) is additive and non-destructive -- every existing value
already fits in 4 characters, so no data is altered or lost, and nothing else that
reads this column (the blank-type quotation screen's item codes are at most 4 chars)
is affected.

    py -3.14 manage.py widen_quot_dat_icode            # show the SQL
    py -3.14 manage.py widen_quot_dat_icode --apply    # run it
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

CHECK_SQL = (
    "SELECT CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS "
    "WHERE TABLE_NAME = 'quot_dat' AND COLUMN_NAME = 'i_code'"
)
ALTER_SQL = "ALTER TABLE quot_dat ALTER COLUMN i_code VARCHAR(10) NULL"


class Command(BaseCommand):
    help = "Widen quot_dat.i_code from VARCHAR(4) to VARCHAR(10) (SQL Server, SP_MACHINE)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Run the ALTER (default: only print it).")

    def handle(self, *args, apply=False, **options):
        if "legacy" not in connections.databases:
            raise CommandError("The SQL Server ('legacy') connection isn't configured in .env.")
        connection = connections["legacy"]
        if connection.vendor != "microsoft":
            raise CommandError("The 'legacy' connection is not SQL Server.")
        with connection.cursor() as cursor:
            cursor.execute(CHECK_SQL)
            row = cursor.fetchone()
            current = row[0] if row else None
            if current is None:
                raise CommandError("quot_dat.i_code not found -- check the connection / table name.")
            if current >= 10:
                self.stdout.write(self.style.SUCCESS(f"quot_dat.i_code is already VARCHAR({current}). Nothing to do."))
                return
            if not apply:
                self.stdout.write(f"-- current: VARCHAR({current})\n{ALTER_SQL};\n")
                self.stdout.write(self.style.WARNING("Nothing was run. Add --apply to run it."))
                return
            cursor.execute(ALTER_SQL)
            cursor.execute(CHECK_SQL)
            new_len = cursor.fetchone()[0]
        self.stdout.write(self.style.SUCCESS(f"quot_dat.i_code is now VARCHAR({new_len})."))

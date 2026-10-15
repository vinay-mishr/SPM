"""
Create the Quotation module's two helper tables in the SQL Server (SP_MACHINE) database:

  web_quot_audit   -- who created / changed / confirmed each quotation, and when
  web_quot_submit  -- one-time request tokens (a double click or retry never saves twice)

Both are NEW tables. The command only ever runs the CREATE statements below, each guarded
by "IF OBJECT_ID(...) IS NULL", so it never alters or drops anything and is safe to run
again. Without --apply it only prints the SQL.

    py -3.14 manage.py create_quotation_tables            # show the SQL
    py -3.14 manage.py create_quotation_tables --apply    # create the tables
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

STATEMENTS = [
    """IF OBJECT_ID(N'dbo.web_quot_audit', N'U') IS NULL
CREATE TABLE dbo.web_quot_audit (
    id           INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_web_quot_audit PRIMARY KEY,
    quot_no      VARCHAR(6)   NOT NULL CONSTRAINT UQ_web_quot_audit_quot_no UNIQUE,
    created_by   VARCHAR(150) NULL,
    created_at   DATETIME2    NULL,
    updated_by   VARCHAR(150) NULL,
    updated_at   DATETIME2    NULL,
    confirmed_by VARCHAR(150) NULL,
    confirmed_at DATETIME2    NULL
);""",
    """IF OBJECT_ID(N'dbo.web_quot_submit', N'U') IS NULL
CREATE TABLE dbo.web_quot_submit (
    id         INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_web_quot_submit PRIMARY KEY,
    token      VARCHAR(64)   NOT NULL CONSTRAINT UQ_web_quot_submit_token UNIQUE,
    action     VARCHAR(10)   NOT NULL,
    quot_no    VARCHAR(6)    NOT NULL CONSTRAINT DF_web_quot_submit_quot_no DEFAULT (''),
    status     VARCHAR(10)   NOT NULL CONSTRAINT DF_web_quot_submit_status DEFAULT ('pending'),
    response   NVARCHAR(MAX) NOT NULL CONSTRAINT DF_web_quot_submit_response DEFAULT (N'{}'),
    username   VARCHAR(150)  NULL,
    created_at DATETIME2     NOT NULL
);""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_web_quot_submit_quot_no'
               AND object_id = OBJECT_ID(N'dbo.web_quot_submit'))
CREATE INDEX IX_web_quot_submit_quot_no ON dbo.web_quot_submit (quot_no);""",
]


class Command(BaseCommand):
    help = "Create the Quotation module's helper tables (web_quot_audit, web_quot_submit) in SQL Server."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Run the SQL (default: only print it).")

    def handle(self, *args, apply=False, **options):
        sql = "\nGO\n".join(STATEMENTS)
        if not apply:
            self.stdout.write(sql + "\nGO\n")
            self.stdout.write(self.style.WARNING("Nothing was run. Add --apply to create the tables."))
            return
        if "legacy" not in connections.databases:
            raise CommandError("The SQL Server ('legacy') connection isn't configured in .env.")
        connection = connections["legacy"]
        if connection.vendor != "microsoft":
            raise CommandError("The 'legacy' connection is not SQL Server.")
        with connection.cursor() as cursor:
            for statement in STATEMENTS:
                cursor.execute(statement)
            cursor.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME IN ('web_quot_audit', 'web_quot_submit')"
            )
            found = sorted(r[0] for r in cursor.fetchall())
        self.stdout.write(self.style.SUCCESS(f"Tables present in SQL Server: {', '.join(found)}"))

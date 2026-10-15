from django.db import models


class Ledger(models.Model):
    """
    General ledger account — the existing ``gled_mst`` table of the old software
    (SP_MACHINE). Old VFP form: ``do form gl`` (GENERAL LEDGER MASTER).

    ``managed = False``: Django never creates, alters or drops this table.
    ``gcode`` (ledger code) is unique in the real data, unlike several other
    legacy tables, so it is used as the primary key.
    """

    ledger_code = models.CharField("ledger code", db_column="gcode", max_length=4, primary_key=True)
    description = models.CharField(db_column="gdesc", max_length=40, blank=True, null=True)
    opening_balance = models.DecimalField(
        "opening balance", db_column="gyob", max_digits=13, decimal_places=2, blank=True, null=True
    )
    group_code = models.DecimalField(
        "ledger group", db_column="gr_code", max_digits=5, decimal_places=0, blank=True, null=True
    )
    group_name = models.CharField(db_column="grp_name", max_length=40, blank=True, null=True)
    gl_type = models.CharField("group (tree)", db_column="gl_type", max_length=10, blank=True, null=True)
    uname = models.CharField(db_column="cuname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "gled_mst"
        ordering = ["description"]
        verbose_name = "ledger"
        verbose_name_plural = "ledgers"
        permissions = [
            ("change_general_ledger", "Can change general ledger"),
            ("change_ledger_opening_balance", "Can change ledger opening balance"),
        ]

    def __str__(self):
        return f"{self.ledger_code} {self.description or ''}".strip()

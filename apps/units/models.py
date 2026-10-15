from django.db import models


class Unit(models.Model):
    """
    Unit of measure — the existing ``unit`` table of the old software (SP_MACHINE).
    Old VFP form: UNIT MASTER (BOX, KG, LIT, MTR, NUM, PCS, ...).

    ``managed = False``: Django never creates, alters or drops this table.
    The table has no key of its own; ``name`` (the unit shown on the old
    screen) is unique in the real data, so it is used as the primary key.
    """

    name = models.CharField("unit", db_column="name", max_length=3, primary_key=True)
    code = models.CharField(db_column="code", max_length=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "unit"
        ordering = ["name"]
        verbose_name = "unit"
        verbose_name_plural = "units"
        permissions = [("change_unit_master", "Can change unit master")]

    def __str__(self):
        return self.name or ""

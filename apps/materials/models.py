from django.db import models


class Material(models.Model):
    """
    Material — the existing ``mat_mst`` table of the old software (SP_MACHINE).

    ``managed = False``: Django never creates, alters or drops this table. The table
    has no key of its own; ``code`` (first letter/digit of the name + a 3-digit number,
    e.g. "A001", the same pattern as Party Master and Supervisor Master) is unique and
    used as the key.

    No other table in SP_MACHINE was found to reference a material by this code (the
    free-text "material" columns on several transaction tables hold typed descriptions,
    not this code), so there is nothing to check before deleting one.
    """

    code = models.CharField("material code", db_column="code", max_length=4, primary_key=True)
    name = models.CharField(db_column="name", max_length=20, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=25, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "mat_mst"
        ordering = ["name"]
        verbose_name = "material"
        verbose_name_plural = "materials"

    def __str__(self):
        return f"{self.code} {self.name or ''}".strip()

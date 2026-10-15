from django.db import models


class Supervisor(models.Model):
    """
    Supervisor — the existing ``sup_mst`` table of the old software (SP_MACHINE).

    ``managed = False``: Django never creates, alters or drops this table. The table
    has no key of its own; ``code`` (first letter of the name + a 3-digit number, e.g.
    "G001", the same pattern as Party Master) is unique and used as the key.
    """

    code = models.CharField("supervisor code", db_column="code", max_length=4, primary_key=True)
    name = models.CharField(db_column="name", max_length=20, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=25, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "sup_mst"
        ordering = ["name"]
        verbose_name = "supervisor"
        verbose_name_plural = "supervisors"

    def __str__(self):
        return f"{self.code} {self.name or ''}".strip()

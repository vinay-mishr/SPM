from django.db import models


class MarketingManager(models.Model):
    """
    Marketing manager — the existing ``mm_mst`` table of the old software (SP_MACHINE).

    ``managed = False``: Django never creates, alters or drops this table. The table has
    no key of its own; ``mcode`` (2-digit code: 01, 02, ...) is unique and used as the key.
    Parties refer to a manager through ``cust_mst.cmm`` (Party Master's MKT MANAGER).
    """

    code = models.CharField("manager code", db_column="mcode", max_length=2, primary_key=True)
    name = models.CharField("manager name", db_column="mname", max_length=25, blank=True, null=True)
    address_1 = models.CharField("address 1", db_column="add1", max_length=30, blank=True, null=True)
    address_2 = models.CharField("address 2", db_column="add2", max_length=30, blank=True, null=True)
    city = models.CharField(db_column="add3", max_length=30, blank=True, null=True)
    phone = models.CharField(db_column="phoneno", max_length=15, blank=True, null=True)
    mobile = models.CharField("mobile number", db_column="mobile", max_length=15, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "mm_mst"
        ordering = ["name"]
        verbose_name = "marketing manager"
        verbose_name_plural = "marketing managers"

    def __str__(self):
        return f"{self.code} {self.name or ''}".strip()

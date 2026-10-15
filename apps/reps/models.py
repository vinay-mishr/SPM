from django.db import models


class Rep(models.Model):
    """
    Sales representative — the existing ``rep_mst`` table of the old software (SP_MACHINE).

    ``managed = False``: Django never creates, alters or drops this table. The table has
    no key of its own; ``rcode`` (2-digit code) is unique and used as the key. Parties
    refer to a rep through ``cust_mst.crep`` (Party Master's REP CODE).
    Columns not listed here (b_name, t_fm, t_bm, p_add1, p_add2) are left untouched.
    """

    code = models.CharField("rep code", db_column="rcode", max_length=2, primary_key=True)
    name = models.CharField("rep name", db_column="rname", max_length=25, blank=True, null=True)
    father_name = models.CharField("father name", db_column="f_name", max_length=25, blank=True, null=True)
    address_1 = models.CharField("address 1", db_column="add1", max_length=30, blank=True, null=True)
    address_2 = models.CharField("address 2", db_column="add2", max_length=30, blank=True, null=True)
    address_3 = models.CharField("address 3", db_column="add3", max_length=30, blank=True, null=True)
    permanent_location = models.CharField("permanent location", db_column="p_add", max_length=30, blank=True, null=True)
    phone = models.CharField("phone no", db_column="phoneno", max_length=15, blank=True, null=True)
    mobile = models.CharField("mobile number", db_column="mobile", max_length=15, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "rep_mst"
        ordering = ["name"]
        verbose_name = "rep"
        verbose_name_plural = "reps"

    def __str__(self):
        return f"{self.code} {self.name or ''}".strip()

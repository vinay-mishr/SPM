from django.db import models


class Party(models.Model):
    """
    Party master — the existing ``cust_mst`` table of the old software (SP_MACHINE).

    ``managed = False``: Django never creates, alters or drops this table.
    Field names are Django's; ``db_column`` gives the real column names.
    The table has no primary key of its own; ``ccode`` is unique, so it is used.
    ``code`` is the ledger group: S001 Sundry Debtor, S002 Sundry Creditor.
    Columns not listed here are left untouched (new rows get '' / 0 for them).
    """

    party_code = models.CharField("party code", db_column="ccode", max_length=4, primary_key=True)
    group_code = models.CharField("group", db_column="code", max_length=4, blank=True, null=True)
    name = models.CharField(db_column="cname", max_length=40, blank=True, null=True)

    address_1 = models.CharField("address 1", db_column="cadd1", max_length=50, blank=True, null=True)
    address_2 = models.CharField("address 2", db_column="cadd2", max_length=50, blank=True, null=True)
    city = models.CharField(db_column="cadd3", max_length=50, blank=True, null=True)
    address_3 = models.CharField("address 3", db_column="cadd4", max_length=50, blank=True, null=True)
    pin = models.CharField("PIN", db_column="pin", max_length=6, blank=True, null=True)

    state_gcode = models.CharField("state (gstate code)", db_column="gscode", max_length=4, blank=True, null=True)
    state_gst_code = models.CharField("GST state code", db_column="gsname", max_length=40, blank=True, null=True)
    state_name = models.CharField("state name", db_column="stname", max_length=30, blank=True, null=True)

    gst_no = models.CharField("GST no.", db_column="gst_no", max_length=16, blank=True, null=True)
    gst_category = models.CharField("GST category", db_column="cat_na", max_length=15, blank=True, null=True)
    gst_category_code = models.CharField(db_column="cat_cd", max_length=2, blank=True, null=True)

    contact_person_1 = models.CharField(db_column="ccper", max_length=20, blank=True, null=True)
    phone_1 = models.CharField(db_column="cphno", max_length=25, blank=True, null=True)
    mobile_1 = models.CharField(db_column="mobile", max_length=20, blank=True, null=True)
    contact_person_2 = models.CharField(db_column="ccper1", max_length=20, blank=True, null=True)
    phone_2 = models.CharField(db_column="cphno1", max_length=25, blank=True, null=True)
    mobile_2 = models.CharField(db_column="mobile1", max_length=20, blank=True, null=True)
    email = models.CharField(db_column="cbadd3", max_length=30, blank=True, null=True)

    transport = models.CharField(db_column="ctrp", max_length=25, blank=True, null=True)
    credit_days = models.DecimalField(db_column="cr_days", max_digits=3, decimal_places=0, blank=True, null=True)
    active = models.CharField(db_column="active", max_length=1, blank=True, null=True)
    association = models.CharField(db_column="assc", max_length=4, blank=True, null=True)
    supply_type = models.CharField("within / interstate", db_column="cstat", max_length=2, blank=True, null=True)
    permit = models.CharField(db_column="rpermit", max_length=1, blank=True, null=True)
    pdc = models.CharField("PDC", db_column="pdc", max_length=1, blank=True, null=True)

    grade = models.CharField(db_column="grade", max_length=1, blank=True, null=True)

    mkt_manager_code = models.CharField(db_column="cmm", max_length=2, blank=True, null=True)
    mkt_manager_name = models.CharField(db_column="m_name", max_length=25, blank=True, null=True)
    rep_code = models.CharField(db_column="crep", max_length=2, blank=True, null=True)
    rep_name = models.CharField(db_column="r_name", max_length=25, blank=True, null=True)

    # Opening balance (Opening Balance Master): positive = Debit, negative = Credit.
    opening_balance = models.DecimalField(
        "opening balance", db_column="cyob", max_digits=13, decimal_places=2, blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "cust_mst"
        ordering = ["name"]
        verbose_name = "party"
        verbose_name_plural = "parties"
        permissions = [("change_opening_balance", "Can change opening balance")]

    def __str__(self):
        return f"{self.party_code} {self.name or ''}".strip()

    @property
    def is_active(self):
        """Only 'N' means inactive in the old data (Y, A and blank are active)."""
        return (self.active or "").strip().upper() != "N"

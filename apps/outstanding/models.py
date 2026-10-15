from django.db import models


class Bill(models.Model):
    """
    Customer bill — the existing ``bill`` table of the old software (SP_MACHINE).

    Previous Outstanding (old VFP form BILLPY) adds / changes / removes rows here:
    DIV "OL" = previous years, "SP" = current year.

    ``managed = False``: Django never creates, alters or drops this table.
    The table has no key; a bill is identified by DIV + BILL NO + PARTY, so this
    module always filters on all three (``bill_no`` is only declared as Django's
    primary key because Django requires one — never rely on it alone).
    """

    bill_no = models.CharField("invoice no", db_column="bill_no", max_length=5, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    bill_date = models.DateField("invoice date", db_column="b_date", blank=True, null=True)
    party_code = models.CharField("party", db_column="p_code", max_length=4, blank=True, null=True)
    net_amount = models.DecimalField("balance amt", db_column="n_amount", max_digits=10, decimal_places=2, blank=True, null=True)
    amount = models.DecimalField(db_column="amount", max_digits=10, decimal_places=2, blank=True, null=True)
    cash_discount = models.DecimalField("cash dis", db_column="c_dis", max_digits=10, decimal_places=2, blank=True, null=True)
    amount_received = models.DecimalField(db_column="amt_rcd", max_digits=10, decimal_places=2, blank=True, null=True)
    payment_received = models.CharField(db_column="pmt_rcd", max_length=1, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "bill"
        ordering = ["bill_date", "bill_no"]
        verbose_name = "previous outstanding bill"
        verbose_name_plural = "previous outstanding bills"
        permissions = [
            ("change_previous_outstanding", "Can change previous outstanding"),
            ("change_creditor_outstanding", "Can change previous creditor outstanding"),
        ]

    def __str__(self):
        return f"{self.div or ''}/{self.bill_no} {self.party_code or ''}".strip()

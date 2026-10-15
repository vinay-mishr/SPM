from django.db import models


class Item(models.Model):
    """
    Item master — the existing ``item`` table of the old software (SP_MACHINE).

    ``managed = False``: Django never creates, alters or drops this table.
    Field names are Django's; ``db_column`` gives the real column names.
    The table has no primary key of its own, so the item code (i_code) is used.
    New codes are 4-digit, zero-padded (``services.next_item_code``).
    """

    item_code = models.CharField("item code", db_column="i_code", max_length=10, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    item_name_1 = models.CharField("item name 1", db_column="i_name", max_length=30, blank=True, null=True)
    item_name_2 = models.CharField("item name 2", db_column="i_name2", max_length=35, blank=True, null=True)
    item_name_3 = models.CharField("item name 3", db_column="i_name3", max_length=35, blank=True, null=True)
    unit = models.CharField(db_column="unit", max_length=3, blank=True, null=True)
    hsn_code = models.CharField("HSN code", db_column="hs_code", max_length=8, blank=True, null=True)
    gst_percent = models.DecimalField("GST %", db_column="gs_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    rate = models.DecimalField(db_column="rate", max_digits=9, decimal_places=2, blank=True, null=True)
    time_required = models.DecimalField("time required (min per unit)", db_column="time_reqd", max_digits=10, decimal_places=2, blank=True, null=True)
    invoice_rate = models.DecimalField("invoice rate", db_column="inv_rt", max_digits=10, decimal_places=2, blank=True, null=True)
    opening_balance = models.DecimalField(
        "opening balance", db_column="op_bal", max_digits=9, decimal_places=2, blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "item"
        ordering = ["item_code"]
        verbose_name = "item"
        verbose_name_plural = "items"

    def __str__(self):
        return f"{self.item_code} {self.item_name_1 or ''}".strip()

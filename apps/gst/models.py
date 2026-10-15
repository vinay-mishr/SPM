from django.db import models


class GstRate(models.Model):
    """
    GST rate bracket -> the sale/purchase ledger accounts it posts tax to -- the
    existing ``gst`` table of the old software (SP_MACHINE). Old VFP form: GST MASTER.

    Each row is one GST % bracket (0, 5, 12, 18, 28 in the real data). For that
    bracket, the twelve ``*_account`` fields hold ledger account codes (``gled_mst``
    / apps.gl.Ledger) to post to for: the sale taxfree account, the purchase taxfree
    account, and -- separately for sale and purchase -- the within-state account +
    CGST + SGST, and the interstate account + IGST.

    ``managed = False``: Django never creates, alters or drops this table. ``rate``
    (``gst_rt``) has no unique constraint in the real table, but is unique among the
    real, non-blank rows and is used as the primary key; two fully-blank duplicate
    rows and a stray blank-duplicate 12% row were removed from the live data (see the
    session that added this module) since they carried zero information.
    """

    rate = models.DecimalField("GST %", db_column="gst_rt", max_digits=5, decimal_places=2, primary_key=True)

    sale_taxfree_account = models.CharField(
        "sale taxfree A/C", db_column="sl_code", max_length=4, blank=True, null=True,
    )
    sale_account = models.CharField(
        "sale A/C (within state)", db_column="sale_code", max_length=4, blank=True, null=True,
    )
    sale_cgst_account = models.CharField(
        "sale CGST A/C", db_column="sale_cgst", max_length=4, blank=True, null=True,
    )
    sale_sgst_account = models.CharField(
        "sale SGST A/C", db_column="sale_sgst", max_length=4, blank=True, null=True,
    )
    sale_interstate_account = models.CharField(
        "sale A/C (interstate)", db_column="sali_code", max_length=4, blank=True, null=True,
    )
    sale_igst_account = models.CharField(
        "sale IGST A/C", db_column="sale_igst", max_length=4, blank=True, null=True,
    )

    purchase_taxfree_account = models.CharField(
        "purchase taxfree A/C", db_column="tf_code", max_length=4, blank=True, null=True,
    )
    purchase_account = models.CharField(
        "purchase A/C (within state)", db_column="pur_code", max_length=4, blank=True, null=True,
    )
    purchase_cgst_account = models.CharField(
        "purchase CGST A/C", db_column="pur_cgst", max_length=4, blank=True, null=True,
    )
    purchase_sgst_account = models.CharField(
        "purchase SGST A/C", db_column="pur_sgst", max_length=4, blank=True, null=True,
    )
    purchase_interstate_account = models.CharField(
        "purchase A/C (interstate)", db_column="puri_code", max_length=4, blank=True, null=True,
    )
    purchase_igst_account = models.CharField(
        "purchase IGST A/C", db_column="pur_igst", max_length=4, blank=True, null=True,
    )

    class Meta:
        managed = False
        db_table = "gst"
        ordering = ["rate"]
        verbose_name = "GST rate"
        verbose_name_plural = "GST rates"
        permissions = [("change_gst_master", "Can change GST master")]

    def __str__(self):
        return f"{self.rate}%"

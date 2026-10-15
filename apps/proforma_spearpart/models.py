from django.db import models


class ProformaSpearpartExtra(models.Model):
    """
    Performa Invoice (Spearpart) (old VFP form "gPER4", bill_type='P' on ``g_per``/
    ``p_mst`` -- separate tables and counter from apps.proforma_invoice's own 'G'
    type) fields with no column on ``g_per``: "PL No." / "PL Date" and "Others"
    appear on the real form (second reference screenshot) but are never written by
    the real ``rpldata`` save routine this module was built from -- confirmed by
    reading it line by line, no ``.tplno``/``.tplnodt``/``.tothers`` save statement
    exists anywhere in it. Kept locally the same way apps.gst_invoice.models.
    GstInvoiceExtra keeps its own no-column fields, keyed by the same bill_no
    (unique within bill_type='P' on g_per, not globally -- see services.py).
    """

    bill_no = models.CharField("P.F. no", max_length=10, unique=True)
    pl_no = models.CharField("PL no", max_length=20, blank=True)
    pl_date = models.DateField("PL date", null=True, blank=True)
    others = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Performa Invoice (Spearpart) extra fields"

    def __str__(self):
        return self.bill_no

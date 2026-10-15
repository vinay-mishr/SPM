from django.db import models


class DebitNote(models.Model):
    """Purchase GST debit note. The narration is the four-line 'Reason for issuing document'."""

    dn_no = models.CharField("D.N. no", max_length=10, unique=True)
    dn_date = models.DateField("D.N. date")
    invoice_no = models.CharField("invoice no", max_length=20, blank=True)
    invoice_date = models.DateField("invoice date", blank=True, null=True)
    party_code = models.CharField("party code", max_length=4)
    party_name = models.CharField("party name", max_length=60, blank=True)
    party_city = models.CharField("party city", max_length=40, blank=True)
    place_of_supply = models.CharField(max_length=40, blank=True)
    narration = models.TextField("reason for issuing document", blank=True)
    taxable = models.JSONField(default=dict)
    gst = models.JSONField(default=dict)
    cess = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_rounded = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gr_no = models.CharField("G.R. no", max_length=20, blank=True)
    gr_date = models.DateField("G.R. date", blank=True, null=True)
    transport = models.CharField(max_length=40, blank=True)
    freight = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    freight_gst_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    kind = models.CharField(max_length=1, default="E")
    locked = models.BooleanField(default=False)
    uname = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-dn_date", "-dn_no"]

    def __str__(self):
        return f"D.N. {self.dn_no}"


class DebitNoteCounter(models.Model):
    """Last debit note number issued. One row, read and updated under a row lock."""

    last_no = models.PositiveIntegerField(default=0)
from .item_models import DebitNoteItemLine  # noqa: F401


from .legacy_models import DebitNoteBill  # noqa: E402,F401

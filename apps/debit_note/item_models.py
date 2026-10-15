from django.db import models

from .models import DebitNote


class DebitNoteItemLine(models.Model):
    """One item on an item-based debit note (VFP DEBIT NOTE grid)."""

    note = models.ForeignKey(DebitNote, related_name="item_lines", on_delete=models.CASCADE)
    line_no = models.PositiveIntegerField()
    item_code = models.CharField(max_length=10)
    item_name = models.CharField(max_length=60, blank=True)
    hsn_code = models.CharField(max_length=8, blank=True)
    unit = models.CharField(max_length=3, blank=True)
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    mrp = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    dis_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    gst_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ["line_no"]

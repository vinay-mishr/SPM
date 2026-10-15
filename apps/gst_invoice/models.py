from django.db import models


class GstInvoiceExtra(models.Model):
    """
    GST Invoice (old VFP form INVOICE / GSTBILL5) fields that have no column on
    the legacy ``bill`` table -- confirmed against the real table's own schema
    (``INFORMATION_SCHEMA.COLUMNS``; a few others e.g. Vehicle No (``vehi_no``)
    turned out to already exist there and are saved straight to the legacy row
    instead). Kept locally (this project's SQLite "default" database) the same
    way apps.debit_note.models.DebitNote keeps its own ``place_of_supply`` --
    the legacy row is still the header of record, found by ``bill_no``.
    """

    bill_no = models.CharField("GST bill no", max_length=10, unique=True)
    date_of_supply = models.DateField(null=True, blank=True)
    time_of_supply = models.CharField(max_length=10, blank=True)
    place_of_supply = models.CharField(max_length=40, blank=True)
    eway_no = models.CharField("e-way number", max_length=20, blank=True)
    eway_date = models.DateField("e-way date", null=True, blank=True)
    reverse_charge = models.BooleanField("tax payable on reverse charge", default=False)

    # The legacy ``bill`` row only ever stores the freight AMOUNT (fr_amt/fr_amt1),
    # never which ledger account it was credited to -- unlike the GST sale
    # buckets, which read their ledger code from apps.gst.GstRate. Historic real
    # trans rows for this bill type show freight consistently credited to a
    # ledger code the operator picked each time (not a fixed global), so the Add
    # form asks for it and it's kept here so Modify/View can show what was used.
    freight_ledger_code = models.CharField(max_length=4, blank=True)
    freight_gst_ledger_code = models.CharField(max_length=4, blank=True)

    class Meta:
        verbose_name = "GST invoice extra fields"

    def __str__(self):
        return self.bill_no

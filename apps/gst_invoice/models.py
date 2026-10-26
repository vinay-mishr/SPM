import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


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


def _new_share_token():
    return secrets.token_urlsafe(24)  # ~32 url-safe characters, not sequential/guessable


class GstInvoiceShareLink(models.Model):
    """
    A public, unguessable link to one GST invoice's PDF, for sharing outside the
    app (e.g. over WhatsApp) without the recipient needing to log in -- same
    convention as apps.purchase_orders.models.PurchaseOrderShareLink.

    New table, managed by Django on the app's own "default" database -- not the
    legacy SP_MACHINE database, which this data has no counterpart in.
    """

    token = models.CharField(max_length=64, unique=True, default=_new_share_token, editable=False)
    bill_no = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False, help_text="Tick to invalidate this link immediately.")

    class Meta:
        indexes = [models.Index(fields=["bill_no"])]
        verbose_name = "GST invoice share link"
        verbose_name_plural = "GST invoice share links"

    def __str__(self):
        return f"{self.bill_no} -> {self.token[:8]}…"

    def is_valid(self):
        return not self.revoked and self.expires_at > timezone.now()

    @classmethod
    def get_or_create_for(cls, bill_no):
        existing = cls.objects.filter(bill_no=bill_no, revoked=False, expires_at__gt=timezone.now()).first()
        if existing:
            return existing
        days = getattr(settings, "PO_SHARE_LINK_EXPIRY_DAYS", 30)
        return cls.objects.create(bill_no=bill_no, expires_at=timezone.now() + timezone.timedelta(days=days))

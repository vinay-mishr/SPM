# Spare Part Invoice (old VFP form "gstbill7", bill_type='P') has no models of its
# own: its header lives in the same ``bill`` table as apps.gst_invoice ('G' type),
# sharing the very same ``inv_no.gb_inv_no`` numbering counter (confirmed from the
# real VFP source: both forms run ``nn=allt(str(gb_inv_no+1))`` against the same
# column) -- so bill_no is unique across *both* bill types, never just within one.
# The handful of fields that have no column on ``bill`` (date/time/place of supply,
# e-way no/date, reverse charge) are the same gap apps.gst_invoice hit, so this app
# reuses apps.gst_invoice.models.GstInvoiceExtra directly rather than duplicating an
# identical side table keyed by the same (globally unique) bill_no.

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def _new_share_token():
    return secrets.token_urlsafe(24)  # ~32 url-safe characters, not sequential/guessable


class SpareInvoiceShareLink(models.Model):
    """
    A public, unguessable link to one Spare Part invoice's PDF, for sharing
    outside the app (e.g. over WhatsApp) without the recipient needing to log
    in -- same convention as apps.purchase_orders.models.PurchaseOrderShareLink.

    New table, managed by Django on the app's own "default" database -- not the
    legacy SP_MACHINE database, which this data has no counterpart in.
    """

    token = models.CharField(max_length=64, unique=True, default=_new_share_token, editable=False)
    bill_no = models.CharField(max_length=10)
    div = models.CharField(max_length=2, blank=True)
    vou_no = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False, help_text="Tick to invalidate this link immediately.")

    class Meta:
        indexes = [models.Index(fields=["bill_no"])]
        verbose_name = "Spare Part invoice share link"
        verbose_name_plural = "Spare Part invoice share links"

    def __str__(self):
        return f"{self.bill_no} -> {self.token[:8]}…"

    def is_valid(self):
        return not self.revoked and self.expires_at > timezone.now()

    @classmethod
    def get_or_create_for(cls, bill_no, div, vou_no):
        existing = cls.objects.filter(
            bill_no=bill_no, div=div or "", vou_no=vou_no or "", revoked=False, expires_at__gt=timezone.now(),
        ).first()
        if existing:
            return existing
        days = getattr(settings, "PO_SHARE_LINK_EXPIRY_DAYS", 30)
        return cls.objects.create(
            bill_no=bill_no, div=div or "", vou_no=vou_no or "", expires_at=timezone.now() + timezone.timedelta(days=days),
        )

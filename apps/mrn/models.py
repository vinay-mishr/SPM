"""
MRN Entry (Material Receipt Note) — old VFP form "MRN ENTRY" / report "grn5".

* ``MrnData`` is the existing, live ``mrn_dat`` table (72 real records going back
  months as of this writing) -- one row per MRN: the party, dates, challan/
  invoice references, and the MRN's total amount/GST. ``managed = False``:
  Django never creates, alters or drops it.

* Line items live in the existing ``imaster`` table (``apps.purchase_orders.
  models.ItemMasterTransaction``), confirmed against real data -- NOT a new
  table. An earlier version of this module incorrectly concluded no such table
  existed (``mrn_dat1`` and ``mrntemp`` both looked like candidates and both
  turned out to be empty/unused) and created one; that table has been removed
  again. See ItemMasterTransaction's own docstring for the full story.
"""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class InvNo(models.Model):
    """
    The old software's shared numbering-counter row -- one single row, several
    "next number" counters for different documents. Only the one MRN Entry
    needs (``sp_mrn_no``) is mapped; the rest are left untouched (same
    convention as Part Master's own unmapped columns).
    """

    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    next_mrn_no = models.DecimalField(db_column="sp_mrn_no", max_digits=10, decimal_places=0)

    class Meta:
        managed = False
        db_table = "inv_no"
        verbose_name = "document numbering counter"


class MrnData(models.Model):
    """
    MRN header + totals — the existing ``mrn_dat`` table. See the module
    docstring: this table has never stored line items, only the MRN-level
    total amount and GST.

    A large block of GST-slab (0/5/12/18/28%), surcharge, CESS, CST/VAT-era
    and other charge columns exist on the real table (``adj1-4``, ``pur2``-
    ``pur13``/``vat2``-``vat13``, ``cess_amt``, ``shc_amt``, ``s_tax``,
    ``cform``, ``due_dt``, ``diff_amt``, ``ca_cr``, ``pur_type``, ...) whose
    exact current business meaning could not be confirmed from the supplied
    legacy code alone -- left unmapped here rather than guessed, same as the
    project's existing convention for this kind of ambiguity (see e.g.
    PurchaseOrderHeader's own docstring). A future pass can map them once
    confirmed.
    """

    # mrn_no as the Django primary key (not a surrogate "id") -- same convention
    # as PurchaseOrderHeader.po_no: the table has no real key of its own, but
    # using an actually-existing column instead of an invented one means model
    # instances (header.save()/.delete()/.first()) work without Django trying
    # to SELECT a column that doesn't exist. Division isn't part of this key,
    # so -- same caveat as PurchaseOrderHeader -- every query here still
    # filters on (div, mrn_no) together, never mrn_no alone.
    mrn_no = models.CharField("MRN no", db_column="mrn_no", max_length=6, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    mrn_date = models.DateField("MRN date", db_column="mrn_dt", blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    bill_no = models.CharField("invoice no", db_column="bill_no", max_length=8, blank=True, null=True)
    bill_date = models.DateField("invoice date", db_column="b_date", blank=True, null=True)
    challan_no = models.CharField(db_column="ch_no", max_length=8, blank=True, null=True)
    challan_date = models.DateField(db_column="ch_dt", blank=True, null=True)
    transport = models.CharField(db_column="veh_no", max_length=20, blank=True, null=True)
    gr_no = models.CharField("G.R. no", db_column="gr_no", max_length=15, blank=True, null=True)
    gr_date = models.DateField("G.R. date", db_column="gr_dt", blank=True, null=True)
    check_po = models.CharField("check PO Y/N", db_column="chk_po", max_length=1, blank=True, null=True)
    remarks = models.CharField(db_column="remk2", max_length=40, blank=True, null=True)
    other_charge_1 = models.DecimalField("other charges 1", db_column="oth_chr", max_digits=10, decimal_places=2, blank=True, null=True)
    other_charge_2 = models.DecimalField("other charges 2", db_column="oth_chr1", max_digits=10, decimal_places=2, blank=True, null=True)
    amount = models.DecimalField("total amount", db_column="amount", max_digits=10, decimal_places=2, blank=True, null=True)
    net_amount = models.DecimalField(db_column="n_amount", max_digits=10, decimal_places=2, blank=True, null=True)
    gst_amount = models.DecimalField(db_column="tax_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    mrn_closed = models.CharField("MRN closed (Y/N)", db_column="mrn_cl", max_length=1, blank=True, null=True)
    ac_transferred = models.CharField("A/C transfer (Y/N)", db_column="ac_tf", max_length=1, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "mrn_dat"
        ordering = ["-mrn_date", "-mrn_no"]
        verbose_name = "MRN"
        verbose_name_plural = "MRNs"
        permissions = [("change_mrn", "Can add, modify, delete or close an MRN")]

    def __str__(self):
        return f"{(self.div or '').strip()}/{self.mrn_no}"


def _new_share_token():
    return secrets.token_urlsafe(24)  # ~32 url-safe characters, not sequential/guessable


class MrnShareLink(models.Model):
    """
    A public, unguessable link to one MRN's PDF, for sharing outside the app
    (e.g. over WhatsApp) without the recipient needing to log in -- same
    convention as apps.purchase_orders.models.PurchaseOrderShareLink.

    New table, managed by Django on the app's own "default" database -- not the
    legacy SP_MACHINE database, which this data has no counterpart in.
    """

    token = models.CharField(max_length=64, unique=True, default=_new_share_token, editable=False)
    div = models.CharField(max_length=2)
    mrn_no = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False, help_text="Tick to invalidate this link immediately.")

    class Meta:
        indexes = [models.Index(fields=["div", "mrn_no"])]
        verbose_name = "MRN share link"
        verbose_name_plural = "MRN share links"

    def __str__(self):
        return f"{self.div}/{self.mrn_no} -> {self.token[:8]}…"

    def is_valid(self):
        return not self.revoked and self.expires_at > timezone.now()

    @classmethod
    def get_or_create_for(cls, div, mrn_no):
        """Reuse an existing, still-valid link for this MRN if there is one,
        instead of minting a fresh token (and URL) every time it's shared."""
        existing = cls.objects.filter(div=div, mrn_no=mrn_no, revoked=False, expires_at__gt=timezone.now()).first()
        if existing:
            return existing
        days = getattr(settings, "PO_SHARE_LINK_EXPIRY_DAYS", 30)
        return cls.objects.create(div=div, mrn_no=mrn_no, expires_at=timezone.now() + timezone.timedelta(days=days))


class MrnAuditLog(models.Model):
    """One row per ADD / MODIFY / CLOSE / DELETE of an MRN: who did it and when."""

    div = models.CharField(max_length=2, blank=True)
    mrn_no = models.CharField(max_length=6)
    action = models.CharField(max_length=10)
    username = models.CharField(max_length=150, blank=True)
    action_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-action_at", "-id"]
        verbose_name = "MRN audit log"

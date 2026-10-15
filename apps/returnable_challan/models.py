"""
GST Returnable Challan -- legacy VFP "GST RETURNABLE CHALLAN ENTRY" (chl7 / gchl8) and its
report gchl1.frx. Save rules confirmed from D:/SPM/chl7.SCT.

* InvNo         -- the shared counter row (inv_no.gchl_no).
* GchlHeader    -- gchl_mst. Only challans with type 'I' belong to this screen.
* GchlLine      -- gchl_dat. Lines saved with type 'I', stts 'B' (pending).
Saving does not touch stock (the legacy save routine doesn't either).

2026-10-08: extended to match the real VFP "chl5"/"GCHL7" save routine --
confirmed against live data that this screen's own challans (all 15 real
gchl_mst rows) actually carry GST (``amount`` is pre-tax, ``n_amount`` is the
GST-inclusive net), and that their item lines live in ``imaster``
(apps.purchase_orders.models.ItemMasterTransaction, filtered on chl_no and
stts='S'), not gchl_dat (which has only 2 stray rows, unrelated to any of
the 15 real challans). GchlHeader gained the missing GST-bucket/net-amount
columns below; GchlLine is left as-is (still read by pending_challan_report)
but is no longer where this screen's own items are saved. No ``trans``
ledger postings are made here -- the real rpldata for this form doesn't
make any either.
"""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def _new_share_token():
    return secrets.token_urlsafe(24)  # ~32 url-safe characters, not sequential/guessable


class InvNo(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    next_gchl_no = models.DecimalField(db_column="gchl_no", max_digits=10, decimal_places=0)

    class Meta:
        managed = False
        db_table = "inv_no"
        verbose_name = "document numbering counter"


class GchlHeader(models.Model):
    chl_no = models.CharField("challan no", db_column="chl_no", max_length=6, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    chl_date = models.DateField("challan date", db_column="chl_dt", blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    ord_no = models.CharField("order no", db_column="ord_no", max_length=15, blank=True, null=True)
    ord_date = models.DateField("order date", db_column="ord_dt", blank=True, null=True)
    check_order = models.CharField("check order", db_column="chk_ord", max_length=1, blank=True, null=True)
    remarks = models.CharField(db_column="remk2", max_length=100, blank=True, null=True)
    mode = models.CharField("mode of dispatch", db_column="mode", max_length=20, blank=True, null=True)
    vehicle_no = models.CharField("vehicle no", db_column="lr_no", max_length=20, blank=True, null=True)
    supply_date = models.DateField("date of supply", db_column="rem_date", blank=True, null=True)
    supply_time = models.CharField("time of supply", db_column="rem_time", max_length=30, blank=True, null=True)
    place_of_supply = models.CharField("place of supply", db_column="p_sup", max_length=20, blank=True, null=True)
    phone = models.CharField(db_column="phno", max_length=20, blank=True, null=True)
    amount = models.DecimalField("taxable amount", db_column="amount", max_digits=12, decimal_places=2, blank=True, null=True)
    freight = models.DecimalField(db_column="freight", max_digits=12, decimal_places=2, blank=True, null=True)
    chl_type = models.CharField(db_column="type", max_length=1, blank=True, null=True)

    # Net (GST-inclusive) amount -- the real rpldata saves this un-rounded;
    # there is no separate "rounded" column on gchl_mst (same as the real
    # form, whose NET ROUNDED box is display-only, never persisted).
    n_amount = models.DecimalField("net amount", db_column="n_amount", max_digits=12, decimal_places=2, blank=True, null=True)

    # Set by a later "adjust into invoice" step this screen doesn't perform --
    # read-only here (the ADJUSTED list column, and a guard against editing a
    # challan already adjusted), matching the real form's own behaviour.
    adj = models.CharField("adjusted", db_column="adj", max_length=1, blank=True, null=True)
    adjusted_bill_no = models.CharField(db_column="bill_no", max_length=10, blank=True, null=True)

    amt_tf = models.DecimalField("taxable @0%", db_column="amt_tf", max_digits=12, decimal_places=2, blank=True, null=True)
    sal_tf = models.CharField("taxfree ledger A/C", db_column="sal_tf", max_length=4, blank=True, null=True)

    amt5 = models.DecimalField("taxable @5%", db_column="amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_rt5 = models.DecimalField(db_column="cg_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    cg_amt5 = models.DecimalField(db_column="cg_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_rt5 = models.DecimalField(db_column="sg_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    sg_amt5 = models.DecimalField(db_column="sg_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_rt5 = models.DecimalField(db_column="ig_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    ig_amt5 = models.DecimalField(db_column="ig_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    sl_co5 = models.CharField("sale ledger A/C @5%", db_column="sl_co5", max_length=4, blank=True, null=True)
    sc_cg5 = models.CharField(db_column="sc_cg5", max_length=4, blank=True, null=True)
    sc_sg5 = models.CharField(db_column="sc_sg5", max_length=4, blank=True, null=True)
    sc_ig5 = models.CharField(db_column="sc_ig5", max_length=4, blank=True, null=True)

    amt12 = models.DecimalField("taxable @12%", db_column="amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_rt12 = models.DecimalField(db_column="cg_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    cg_amt12 = models.DecimalField(db_column="cg_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_rt12 = models.DecimalField(db_column="sg_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    sg_amt12 = models.DecimalField(db_column="sg_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_rt12 = models.DecimalField(db_column="ig_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    ig_amt12 = models.DecimalField(db_column="ig_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    sl_co12 = models.CharField("sale ledger A/C @12%", db_column="sl_co12", max_length=4, blank=True, null=True)
    sc_cg12 = models.CharField(db_column="sc_cg12", max_length=4, blank=True, null=True)
    sc_sg12 = models.CharField(db_column="sc_sg12", max_length=4, blank=True, null=True)
    sc_ig12 = models.CharField(db_column="sc_ig12", max_length=4, blank=True, null=True)

    amt18 = models.DecimalField("taxable @18%", db_column="amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_rt18 = models.DecimalField(db_column="cg_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    cg_amt18 = models.DecimalField(db_column="cg_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_rt18 = models.DecimalField(db_column="sg_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    sg_amt18 = models.DecimalField(db_column="sg_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_rt18 = models.DecimalField(db_column="ig_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    ig_amt18 = models.DecimalField(db_column="ig_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    sl_co18 = models.CharField("sale ledger A/C @18%", db_column="sl_co18", max_length=4, blank=True, null=True)
    sc_cg18 = models.CharField(db_column="sc_cg18", max_length=4, blank=True, null=True)
    sc_sg18 = models.CharField(db_column="sc_sg18", max_length=4, blank=True, null=True)
    sc_ig18 = models.CharField(db_column="sc_ig18", max_length=4, blank=True, null=True)

    amt28 = models.DecimalField("taxable @28%", db_column="amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_rt28 = models.DecimalField(db_column="cg_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    cg_amt28 = models.DecimalField(db_column="cg_amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_rt28 = models.DecimalField(db_column="sg_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    sg_amt28 = models.DecimalField(db_column="sg_amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_rt28 = models.DecimalField(db_column="ig_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    ig_amt28 = models.DecimalField(db_column="ig_amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    sl_co28 = models.CharField("sale ledger A/C @28%", db_column="sl_co28", max_length=4, blank=True, null=True)
    sc_cg28 = models.CharField(db_column="sc_cg28", max_length=4, blank=True, null=True)
    sc_sg28 = models.CharField(db_column="sc_sg28", max_length=4, blank=True, null=True)
    sc_ig28 = models.CharField(db_column="sc_ig28", max_length=4, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "gchl_mst"
        verbose_name = "GST returnable challan"
        permissions = [("change_challan", "Can add, modify or delete a GST returnable challan")]


class GchlLine(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    chl_no = models.CharField(db_column="chl_no", max_length=6, blank=True, null=True)
    chl_type = models.CharField(db_column="type", max_length=1, blank=True, null=True)
    line_date = models.DateField(db_column="date", blank=True, null=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    item_code = models.CharField(db_column="i_code", max_length=10, blank=True, null=True)
    item_name = models.CharField(db_column="prt_name", max_length=100, blank=True, null=True)
    hsn_code = models.CharField(db_column="hs_code", max_length=8, blank=True, null=True)
    unit = models.CharField(db_column="unit", max_length=3, blank=True, null=True)
    qty = models.DecimalField(db_column="qty", max_digits=12, decimal_places=3, blank=True, null=True)
    rate = models.DecimalField(db_column="rate", max_digits=12, decimal_places=4, blank=True, null=True)
    amount = models.DecimalField(db_column="amount", max_digits=12, decimal_places=2, blank=True, null=True)
    particular = models.CharField(db_column="particular", max_length=100, blank=True, null=True)
    line_no = models.DecimalField(db_column="sno", max_digits=6, decimal_places=0, blank=True, null=True)
    status = models.CharField(db_column="stts", max_length=1, blank=True, null=True)
    ord_no = models.CharField(db_column="ord_no", max_length=15, blank=True, null=True)
    ord_date = models.DateField(db_column="ord_dt", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "gchl_dat"
        verbose_name = "GST returnable challan line"


class GchlShareLink(models.Model):
    """
    A public, unguessable link to one challan's PDF, for sharing outside the
    app (e.g. over WhatsApp) without the recipient needing to log in -- same
    convention as apps.purchase_orders.models.PurchaseOrderShareLink.

    New table, managed by Django on the app's own "default" database -- not
    the legacy SP_MACHINE database, which this data has no counterpart in.
    """

    token = models.CharField(max_length=64, unique=True, default=_new_share_token, editable=False)
    chl_no = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False, help_text="Tick to invalidate this link immediately.")

    class Meta:
        indexes = [models.Index(fields=["chl_no"])]
        verbose_name = "returnable challan share link"
        verbose_name_plural = "returnable challan share links"

    def __str__(self):
        return f"{self.chl_no} -> {self.token[:8]}…"

    def is_valid(self):
        return not self.revoked and self.expires_at > timezone.now()

    @classmethod
    def get_or_create_for(cls, chl_no):
        """Reuse an existing, still-valid link for this challan if there is
        one, instead of minting a fresh token (and URL) every time it's shared."""
        existing = cls.objects.filter(chl_no=chl_no, revoked=False, expires_at__gt=timezone.now()).first()
        if existing:
            return existing
        days = getattr(settings, "PO_SHARE_LINK_EXPIRY_DAYS", 30)
        return cls.objects.create(chl_no=chl_no, expires_at=timezone.now() + timezone.timedelta(days=days))

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class PurchaseOrderHeader(models.Model):
    """
    Purchase Order header — the existing ``pord_mst`` table of the old software
    (SP_MACHINE). Old VFP form: PURCHASE ORDER FORM (``po1``).

    ``managed = False``: Django never creates, alters or drops this table. The table
    has no key of its own; a PO is identified by DIV + ORDER (po_no), so this module
    always filters on both (``po_no`` is only declared as Django's primary key
    because Django requires one -- never rely on it alone).

    ``pord_mst`` also has ~40 GST-slab-breakdown columns (cg_rt5/sg_amt12/sc_ig28/...)
    used by old reports this project doesn't yet reproduce; they are left untouched
    (same convention as Part Master's ``rate1``-style unmapped columns) rather than
    modelled and half-maintained here.
    """

    po_no = models.CharField("PO no", db_column="order", max_length=4, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    order_date = models.DateField("PO date", db_column="ord_date", blank=True, null=True)
    party_code = models.CharField("party", db_column="p_code", max_length=4, blank=True, null=True)
    amount = models.DecimalField(db_column="amount", max_digits=10, decimal_places=2, blank=True, null=True)
    gst_amount = models.DecimalField(db_column="gst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    net_amount = models.DecimalField(db_column="n_amount", max_digits=10, decimal_places=2, blank=True, null=True)
    remarks = models.CharField(db_column="remk2", max_length=30, blank=True, null=True)
    # Previously-unused legacy columns, now surfaced as Payment / Note.
    payment = models.CharField(db_column="remk3", max_length=30, blank=True, null=True)
    note = models.TextField(db_column="particular", blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "pord_mst"
        ordering = ["-order_date", "-po_no"]
        verbose_name = "purchase order"
        verbose_name_plural = "purchase orders"
        permissions = [("change_purchase_order", "Can change purchase order")]

    def __str__(self):
        return f"{self.div or ''}/{self.po_no} {self.party_code or ''}".strip()


class PurchaseOrderItem(models.Model):
    """
    Purchase Order line — the existing ``order`` table of the old software
    (SP_MACHINE). Each row is one part (``part-mst``) ordered on one PO.

    ``managed = False``: Django never creates, alters or drops this table. The table
    has no key of its own -- not even (div, po_no, part_code) is guaranteed unique
    (the same part could in principle be added twice, and the same part_code appears
    across many different POs, so it can't be a primary key either) -- so, like BOM
    Master, a save always replaces *all* line rows for one PO in a single transaction
    rather than updating an individual row; see services.save().

    The ``id`` BigAutoField below is a Django-only surrogate the real table has no
    matching column for: every query against this model MUST use .values()/.values_list()
    (never a plain/bare queryset) and must never .order_by("id") or read .id, or it will
    try to SELECT/ORDER BY a column ("id") that doesn't exist in the real table -- this
    silently 500s (see get_order(), which used to do exactly that).
    """

    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    po_no = models.CharField(db_column="order", max_length=4, blank=True, null=True)
    part_code = models.CharField("part no", db_column="i_code", max_length=10, blank=True, null=True)
    order_date = models.DateField(db_column="date", blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    po_qty = models.DecimalField("P.O. qty", db_column="stock", max_digits=11, decimal_places=3, blank=True, null=True)
    unit = models.CharField(db_column="uom", max_length=3, blank=True, null=True)
    rate = models.DecimalField(db_column="brate", max_digits=10, decimal_places=4, blank=True, null=True)
    discount_percent = models.DecimalField("discount %", db_column="disc_pct", max_digits=5, decimal_places=2, blank=True, null=True)
    despatch_date = models.DateField(db_column="dd_date", blank=True, null=True)
    quantity = models.DecimalField("qty", db_column="stk_qty", max_digits=11, decimal_places=3, blank=True, null=True)
    received_qty = models.DecimalField(db_column="rec_qty", max_digits=13, decimal_places=3, blank=True, null=True)
    hsn_code = models.CharField("HSN code", db_column="hs_code", max_length=8, blank=True, null=True)
    size = models.CharField(db_column="p_size", max_length=12, blank=True, null=True)
    # Item-level remarks (distinct from the header's own Remarks/Payment/Note on
    # PurchaseOrderHeader) -- a previously-unused legacy column, same convention as
    # the header's own Payment/Note fields.
    particulars = models.TextField(db_column="particular", blank=True, null=True)
    cgst_rate = models.DecimalField(db_column="cgst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    cgst_amount = models.DecimalField(db_column="cgst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    sgst_rate = models.DecimalField(db_column="sgst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    sgst_amount = models.DecimalField(db_column="sgst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    igst_rate = models.DecimalField(db_column="igst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    igst_amount = models.DecimalField(db_column="igst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    gst_rate = models.DecimalField(db_column="gst", max_digits=5, decimal_places=2, blank=True, null=True)
    gst_amount = models.DecimalField(db_column="gst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    adjusted = models.CharField(
        "adjustment status", db_column="adj", max_length=1, blank=True, null=True,
        help_text="Blank/space = still open (pending); anything else = closed/adjusted.",
    )
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "order"
        ordering = ["po_no", "part_code"]
        verbose_name = "purchase order line"
        verbose_name_plural = "purchase order lines"

    def __str__(self):
        return f"{self.po_no}/{self.part_code or ''}".strip()


class PartRateHistory(models.Model):
    """
    Historical purchase rate per part — the existing ``rt_mst`` table (30k+ rows).
    Read-only here: used for "LAST RATE" on the PO form and the "PREVIOUS INFO"
    popup (old VFP: ``rt_mst`` filtered on i_code, and ``DO FORM previnfo2``).
    """

    # The real table has no key at all, not even part_code alone. A BigAutoField "id"
    # here (as several other legacy models in this file use) doesn't work for this one
    # because plain (non-.values()) queries against it -- last_rate(), previous_info()
    # -- SELECT that surrogate column, and the real rt_mst table has no "id" column to
    # match it, so those queries fail outright. Marking part_code as the (non-unique)
    # primary key instead keeps those two read paths working, same as BomComponent's
    # part_code / PurchaseOrderHeader's po_no elsewhere in this project.
    part_code = models.CharField(db_column="i_code", max_length=10, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    bill_no = models.CharField(db_column="bill_no", max_length=5, blank=True, null=True)
    po_no = models.CharField(db_column="order", max_length=4, blank=True, null=True)
    order_date = models.DateField(db_column="date", blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    rate = models.DecimalField(db_column="brate", max_digits=10, decimal_places=4, blank=True, null=True)
    quantity = models.DecimalField(db_column="stk_qty", max_digits=11, decimal_places=3, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "rt_mst"
        ordering = ["-order_date"]
        verbose_name = "part rate history"
        verbose_name_plural = "part rate history"


class CreditorOut(models.Model):
    """
    Purchase invoice / MRN billing row — the existing ``cr_out`` table of the old
    software (SP_MACHINE). Old VFP report: PURCHASE REPORT.

    ``managed = False``: Django never creates, alters or drops this table. The table
    has no key of its own; a row is identified by (div, inv_no, mrn_no), so this
    module always filters on those rather than relying on Django's required PK alone.
    """

    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    bill_no = models.CharField("bill no", db_column="inv_no", max_length=10, blank=True, null=True)
    bill_date = models.DateField("bill date", db_column="inv_dt", blank=True, null=True)
    mrn_no = models.CharField(db_column="mrn_no", max_length=6, blank=True, null=True)
    mrn_date = models.DateField(db_column="mrn_dt", blank=True, null=True)
    gross_amount = models.DecimalField(
        "gross amount", db_column="amt", max_digits=10, decimal_places=2, blank=True, null=True,
        help_text="When empty, the old report falls back to mrn_dat.amount for this mrn_no.",
    )
    net_amount = models.DecimalField(db_column="amount", max_digits=10, decimal_places=2, blank=True, null=True)
    job_type = models.CharField(db_column="job_type", max_length=1, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "cr_out"
        ordering = ["mrn_date", "mrn_no"]
        verbose_name = "purchase invoice (MRN billing)"
        verbose_name_plural = "purchase invoices (MRN billing)"

    def __str__(self):
        return f"{self.bill_no or ''}/{self.mrn_no or ''}".strip()


class MrnData(models.Model):
    """
    Material Receipt Note header — the existing ``mrn_dat`` table of the old software
    (SP_MACHINE). Only the columns the Purchase Report needs are mapped here; the real
    table has ~100 more (GST-slab breakdowns, adjustments, etc.) left untouched.
    """

    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    mrn_no = models.CharField(db_column="mrn_no", max_length=6, blank=True, null=True)
    amount = models.DecimalField(db_column="amount", max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "mrn_dat"
        verbose_name = "MRN data"
        verbose_name_plural = "MRN data"


class ItemMasterTransaction(models.Model):
    """
    Item/MRN transaction row — the existing ``imaster`` table of the old software
    (SP_MACHINE). A very wide table (75+ columns, used across several old screens).

    This is also, confirmed by inspecting real data, the actual table MRN Entry's
    item grid is saved into and reloaded from -- *not* a dedicated "MRN items"
    table (none exists; an earlier version of the MRN Entry module in this
    project wrongly assumed one needed to be created from scratch, built one,
    and only line items added through that new table showed up again on
    reopening -- every pre-existing MRN's items, which really do live here,
    didn't). One row per item received under one MRN, found by filtering this
    table on ``mrn_no`` (e.g. MRN "7"'s 4 bearing lines are 4 rows here with
    ``mrn_no="7"``). Only the columns MRN Entry and the Item-Wise Rate List
    report need are mapped; many more exist (adjustment codes, several
    labour/job-costing fields, etc.) and are left untouched, same convention
    as Part Master's own unmapped columns.
    """

    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    item_code = models.CharField("item code", db_column="i_code", max_length=10, blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    bill_no = models.CharField(db_column="bill_no", max_length=9, blank=True, null=True)
    bill_date = models.DateField(db_column="date", blank=True, null=True)
    mrn_date = models.DateField(db_column="m_dat", blank=True, null=True)
    mrn_flag = models.CharField(db_column="mrn", max_length=1, blank=True, null=True)
    quantity = models.DecimalField(db_column="qty", max_digits=12, decimal_places=3, blank=True, null=True)
    po_qty = models.DecimalField(db_column="po_qty", max_digits=11, decimal_places=3, blank=True, null=True)
    rate = models.DecimalField(db_column="rate", max_digits=10, decimal_places=3, blank=True, null=True)

    # --- MRN Entry's own fields (confirmed against real data for MRN "7") -------
    mrn_no = models.CharField("MRN no", db_column="mrn_no", max_length=6, blank=True, null=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    po_div = models.CharField("PO division", db_column="ord_dv", max_length=2, blank=True, null=True)
    po_no = models.CharField("PO no", db_column="order", max_length=4, blank=True, null=True)
    po_date = models.DateField(db_column="po_date", blank=True, null=True)
    qty_rejected = models.DecimalField(db_column="qty_rej", max_digits=12, decimal_places=3, blank=True, null=True)
    unit = models.CharField(db_column="unit", max_length=3, blank=True, null=True)
    size = models.CharField(db_column="p_size", max_length=12, blank=True, null=True)
    hsn_code = models.CharField(db_column="hs_code", max_length=8, blank=True, null=True)
    amount = models.DecimalField(db_column="amount", max_digits=12, decimal_places=2, blank=True, null=True)
    discount_percent = models.DecimalField(db_column="dis", max_digits=5, decimal_places=2, blank=True, null=True)
    discount_amount = models.DecimalField(db_column="dis_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    gst_percent = models.DecimalField(db_column="gst", max_digits=5, decimal_places=2, blank=True, null=True)
    gst_amount = models.DecimalField(db_column="gst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    cgst_rate = models.DecimalField(db_column="cgst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    cgst_amount = models.DecimalField(db_column="cgst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    sgst_rate = models.DecimalField(db_column="sgst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    sgst_amount = models.DecimalField(db_column="sgst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    igst_rate = models.DecimalField(db_column="igst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    igst_amount = models.DecimalField(db_column="igst_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    status = models.CharField("line status", db_column="stts", max_length=1, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    # --- Single Issue Slip / Single Receipt Slip's own fields (see their services) ---
    remarks = models.CharField(db_column="remak", max_length=40, blank=True, null=True)
    invoice_rate = models.DecimalField("invoice rate", db_column="inv_rt", max_digits=10, decimal_places=4, blank=True, null=True)
    received_flag = models.CharField(db_column="recv", max_length=1, blank=True, null=True)

    # --- Single Issue Report's own field -- a separate "sing" flag column
    # (distinct from the chl_no-linked Single Issue Slip rows above: the Single
    # Issue Report's own legacy code filters this table on sing='Y' and bill_no/
    # date instead, with no chl_no/mrn_no involved at all). Currently always
    # blank in this environment's data -- same "unused-so-far legacy screen"
    # situation as Single Issue Slip's own mis_mst table.
    single_issue_flag = models.CharField(db_column="sing", max_length=1, blank=True, null=True)

    # --- GST Debit Note (item-based) -- links this line back to its debit note ---
    debit_note_no = models.CharField("debit note no", db_column="gdb_no", max_length=10, blank=True, null=True)
    debit_note_date = models.DateField("debit note date", db_column="gdb_dt", blank=True, null=True)

    # --- GST Returnable Challan Entry (apps.returnable_challan) -- links this line
    # back to its challan; rows are stts='S' (confirmed against the real chl5
    # rpldata and the 29 real rows already on this table for the 15 real challans).
    chl_no = models.CharField("challan no", db_column="chl_no", max_length=6, blank=True, null=True)
    sno = models.DecimalField("line no", db_column="sno", max_digits=6, decimal_places=0, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "imaster"
        verbose_name = "item/MRN transaction"
        verbose_name_plural = "item/MRN transactions"


def _new_share_token():
    return secrets.token_urlsafe(24)  # ~32 url-safe characters, not sequential/guessable


class PurchaseOrderShareLink(models.Model):
    """
    A public, unguessable link to one Purchase Order's print view, for sharing
    outside the app (e.g. over WhatsApp) without the recipient needing to log in.

    New table, managed by Django on the app's own "default" database -- not the
    legacy SP_MACHINE database, which this data has no counterpart in.
    """

    token = models.CharField(max_length=64, unique=True, default=_new_share_token, editable=False)
    div = models.CharField(max_length=2)
    po_no = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False, help_text="Tick to invalidate this link immediately.")

    class Meta:
        indexes = [models.Index(fields=["div", "po_no"])]
        verbose_name = "purchase order share link"
        verbose_name_plural = "purchase order share links"

    def __str__(self):
        return f"{self.div}/{self.po_no} -> {self.token[:8]}…"

    def is_valid(self):
        return not self.revoked and self.expires_at > timezone.now()

    @classmethod
    def get_or_create_for(cls, div, po_no):
        """Reuse an existing, still-valid link for this PO if there is one,
        instead of minting a fresh token (and URL) every time it's shared."""
        existing = cls.objects.filter(div=div, po_no=po_no, revoked=False, expires_at__gt=timezone.now()).first()
        if existing:
            return existing
        days = getattr(settings, "PO_SHARE_LINK_EXPIRY_DAYS", 30)
        return cls.objects.create(div=div, po_no=po_no, expires_at=timezone.now() + timezone.timedelta(days=days))


class PendingLetterShareLink(models.Model):
    """
    A public, unguessable link to one party's Pending PO Reminder letter (as on
    one run date), for sharing outside the app (e.g. over WhatsApp) without the
    recipient needing to log in -- same purpose as PurchaseOrderShareLink, just
    for the reminder letter (which can cover several POs at once) rather than
    a single PO.
    """

    token = models.CharField(max_length=64, unique=True, default=_new_share_token, editable=False)
    party_code = models.CharField(max_length=4)
    run_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False, help_text="Tick to invalidate this link immediately.")

    class Meta:
        indexes = [models.Index(fields=["party_code", "run_date"])]
        verbose_name = "pending PO reminder share link"
        verbose_name_plural = "pending PO reminder share links"

    def __str__(self):
        return f"{self.party_code}/{self.run_date} -> {self.token[:8]}…"

    def is_valid(self):
        return not self.revoked and self.expires_at > timezone.now()

    @classmethod
    def get_or_create_for(cls, party_code, run_date):
        """Reuse an existing, still-valid link for this party+run date if there
        is one, instead of minting a fresh token (and URL) every time it's shared."""
        existing = cls.objects.filter(
            party_code=party_code, run_date=run_date, revoked=False, expires_at__gt=timezone.now(),
        ).first()
        if existing:
            return existing
        days = getattr(settings, "PO_SHARE_LINK_EXPIRY_DAYS", 30)
        return cls.objects.create(
            party_code=party_code, run_date=run_date, expires_at=timezone.now() + timezone.timedelta(days=days),
        )

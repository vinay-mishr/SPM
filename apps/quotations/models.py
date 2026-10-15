"""
Quotation -- legacy VFP "QUOTATION" list (quot1) and "QUOTATION HEAD" entry form (quot2).

* QuotationHeader -- the existing ``quot_mst`` table (managed=False). This screen owns
  only rows whose ``type`` is blank (the legacy list filters ``TYPE=' '``); rows with
  type 'Q' come from another legacy screen, keep their lines in ``quotdat``, and are
  never modified or deleted here. Quotation numbers are shared by both kinds.
* Lines live in the existing ``quot_dat`` table. It has no key column at all, so it
  has no model: services.py reads, inserts and deletes its rows with parameterised SQL.
* InvNo -- the shared counter row (``inv_no.quot_no``).
* QuotationMeta / QuotationSubmission -- two NEW tables in the same SQL Server database
  (``web_quot_audit``: who created / changed / confirmed a quotation and when;
  ``web_quot_submit``: one-time tokens that stop a repeated click or network retry from
  saving twice). The old software has no counterpart and never reads them. Like every
  legacy table they are managed=False; they are created once by
  ``manage.py create_quotation_tables`` (see that command for the exact SQL).
  Users are recorded by username, as a foreign key can't cross databases.
"""
from django.db import models


class InvNo(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    quot_no = models.DecimalField(db_column="quot_no", max_digits=5, decimal_places=0, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "inv_no"
        verbose_name = "document numbering counter"


class QuotationHeader(models.Model):
    quot_no = models.CharField("quotation no", db_column="quot_no", max_length=6, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    quot_date = models.DateField("quotation date", db_column="quot_dt", blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    party_name = models.CharField(db_column="party", max_length=50, blank=True, null=True)
    city = models.CharField(db_column="city", max_length=30, blank=True, null=True)
    phone = models.CharField(db_column="phno", max_length=20, blank=True, null=True)
    ref_no = models.CharField("reference no", db_column="ref_no", max_length=10, blank=True, null=True)
    ref_date = models.DateField("reference date", db_column="ref_dt", blank=True, null=True)
    due_date = models.DateField(db_column="due_dt", blank=True, null=True)
    kind_attention_1 = models.CharField(db_column="kind", max_length=50, blank=True, null=True)
    kind_attention_2 = models.CharField(db_column="kind1", max_length=50, blank=True, null=True)
    kind_attention_3 = models.CharField(db_column="kind3", max_length=50, blank=True, null=True)
    subject = models.CharField(db_column="subj", max_length=100, blank=True, null=True)
    subject_2 = models.CharField(db_column="subj1", max_length=100, blank=True, null=True)
    description = models.CharField("quotation", db_column="quotation", max_length=30, blank=True, null=True)
    gst_applicable = models.CharField("GST (Y/N)", db_column="yn", max_length=1, blank=True, null=True)
    quot_type = models.CharField(db_column="type", max_length=1, blank=True, null=True)

    amount = models.DecimalField("total amount", db_column="amount", max_digits=12, decimal_places=2, blank=True, null=True)
    discount_amount = models.DecimalField(db_column="dis_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    discount_rate = models.DecimalField(db_column="dis_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    gst_amount = models.DecimalField("GST amount", db_column="i_charge", max_digits=8, decimal_places=2, blank=True, null=True)
    net_amount = models.DecimalField(db_column="n_amount", max_digits=10, decimal_places=2, blank=True, null=True)
    surcharge_amount = models.DecimalField(db_column="sur_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    surcharge_rate = models.DecimalField(db_column="sur_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    party_tax_rate = models.DecimalField(db_column="s_tax", max_digits=5, decimal_places=2, blank=True, null=True)

    # Free-text blocks of the old form (unused by the new screen but kept on modify).
    rates = models.CharField(db_column="rates", max_length=52, blank=True, null=True)
    cst_vat = models.CharField(db_column="cst_vat", max_length=12, blank=True, null=True)
    payment = models.CharField(db_column="payment", max_length=12, blank=True, null=True)
    delivery = models.CharField(db_column="delivery", max_length=12, blank=True, null=True)
    transport = models.CharField(db_column="trans", max_length=12, blank=True, null=True)
    validity = models.CharField(db_column="validity", max_length=12, blank=True, null=True)

    remarks = models.TextField(db_column="parti1", blank=True, null=True)
    term_1 = models.CharField(db_column="remk", max_length=80, blank=True, null=True)
    term_2 = models.CharField(db_column="remk1", max_length=80, blank=True, null=True)
    term_3 = models.CharField(db_column="remk2", max_length=80, blank=True, null=True)
    term_4 = models.CharField(db_column="remk3", max_length=80, blank=True, null=True)
    term_5 = models.CharField(db_column="remk4", max_length=80, blank=True, null=True)
    bank_1 = models.CharField(db_column="remk5", max_length=40, blank=True, null=True)
    bank_2 = models.CharField(db_column="remk6", max_length=40, blank=True, null=True)
    bank_3 = models.CharField(db_column="remk7", max_length=40, blank=True, null=True)
    bank_4 = models.CharField(db_column="remk8", max_length=40, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "quot_mst"
        verbose_name = "quotation"
        verbose_name_plural = "quotations"

    def __str__(self):
        return f"Quotation {self.quot_no}"


class QuotationMeta(models.Model):
    """Audit trail for one quotation (keyed by quotation number)."""

    id = models.AutoField(primary_key=True)
    quot_no = models.CharField(max_length=6, unique=True)
    created_by = models.CharField(max_length=150, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=150, blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    confirmed_by = models.CharField(max_length=150, blank=True, null=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "web_quot_audit"
        verbose_name = "quotation audit record"

    def __str__(self):
        return f"Quotation {self.quot_no} audit"


class QuotationSubmission(models.Model):
    """
    One row per Save / Confirm request token. The entry form gets a fresh token when it
    loads (and after every save); a repeated POST with the same token gets the stored
    result back instead of writing again.
    """

    STATUS_PENDING = "pending"
    STATUS_DONE = "done"

    id = models.AutoField(primary_key=True)
    token = models.CharField(max_length=64, unique=True)
    action = models.CharField(max_length=10)
    quot_no = models.CharField(max_length=6, blank=True, default="")
    status = models.CharField(max_length=10, default=STATUS_PENDING)
    response = models.TextField(blank=True, default="{}")  # JSON text
    username = models.CharField(max_length=150, blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "web_quot_submit"
        indexes = [models.Index(fields=["quot_no"], name="IX_web_quot_submit_quot_no")]
        verbose_name = "quotation submission"

    def __str__(self):
        return f"{self.action} {self.quot_no} ({self.status})"

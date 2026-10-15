"""GST Credit Note (VFP GST CREDIT NOTE / "gcre1" form, "SPEAR PART" item-based variant).

No local Django-side record is kept -- same approach as apps.returnable_challan:
the legacy SQL Server tables ARE the record, read and written directly through
these managed=False models. The header row lives on ``c_bill`` (the real VFP
``use C_bill`` opens this literal table -- a SEPARATE, near-duplicate table
named ``gc_bill`` also exists in this database with 0 rows and is NOT the one
this form uses; confirmed by a real production row already on c_bill with
bill_type='C'). c_bill is shared with the Narration variant of this form
(narration_models.CBillHeader), told apart by ``bill_type`` -- 'C' here, ' '
(a single space) there. Item lines live in the shared ``g_master`` table
(also used by sale bills, challans, etc.), told apart from every other row
there by ``bill_type='C'``.

Column-to-field mapping is confirmed against the live c_bill/g_master schema
(INFORMATION_SCHEMA.COLUMNS) and against the two closest working siblings in
this codebase -- apps.returnable_challan (header+line legacy posting, stts='B'
convention) and apps.debit_note (GST-bucket posting per rate). One mapping is
inferred rather than confirmed: the Add form's "GST BILL / DATE" field (the
original sale invoice this note adjusts) is assumed to be c_bill's chl_no/
chl_dt column pair -- the only unused date-paired column left on the table
that fits; it is never read back for any other purpose here, so a wrong guess
only affects what prints on that one line.

Deliberately NOT done here (same caution as debit_note.legacy_models): no
stock movement on Part (apps.returnable_challan's own challan save doesn't
touch stock either -- there's no confirmed convention for it) and no write to
the customer's outstanding balance (``outstanding.Bill.n_amount``) or any
ledger/trans posting -- none of those rules were available to confirm.
"""
from django.db import models


class InvNo(models.Model):
    """Shared numbering-counter row (``inv_no`` table has one row, one column
    per document type). ``gc_inv_no`` is the column the real GST Credit Note
    Add button reads (``nn = gc_inv_no + 1``) before calling the entry form."""

    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    next_cn_no = models.DecimalField(db_column="gc_inv_no", max_digits=10, decimal_places=0)

    class Meta:
        managed = False
        db_table = "inv_no"
        verbose_name = "document numbering counter"


class GcBillHeader(models.Model):
    bill_no = models.CharField("C.N. no", db_column="bill_no", max_length=5, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    b_date = models.DateField("C.N. date", db_column="b_date", blank=True, null=True)
    ca_cr = models.CharField(db_column="ca_cr", max_length=2, blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    bill_type = models.CharField(db_column="bill_type", max_length=1, blank=True, null=True)
    cstat = models.CharField("within / interstate", db_column="cstat", max_length=1, blank=True, null=True)

    gst_bill_no = models.CharField("GST bill no", db_column="chl_no", max_length=30, blank=True, null=True)
    gst_bill_date = models.DateField("GST bill date", db_column="chl_dt", blank=True, null=True)
    gr_no = models.CharField(db_column="gr_no", max_length=10, blank=True, null=True)
    gr_date = models.DateField(db_column="gr_dt", blank=True, null=True)
    transport = models.CharField(db_column="trans", max_length=30, blank=True, null=True)
    remarks = models.CharField(db_column="remk", max_length=40, blank=True, null=True)

    amount = models.DecimalField("taxable amount", db_column="amount", max_digits=12, decimal_places=2, blank=True, null=True)
    gst_amt = models.DecimalField(db_column="gst_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    n_amount = models.DecimalField("net amount", db_column="n_amount", max_digits=12, decimal_places=2, blank=True, null=True)

    fr_rt = models.DecimalField("freight GST %", db_column="fr_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    fr_amt = models.DecimalField("freight", db_column="fr_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    fr_amt1 = models.DecimalField("GST on freight", db_column="fr_amt1", max_digits=12, decimal_places=2, blank=True, null=True)

    # c_bill's nar1-4 columns are reserved for the Narration variant's own
    # "reason for issuing document" (narration_models.CBillHeader); this form's
    # Add/Less line only has a 4-char ledger-code slot (adj_code1/2) of its own,
    # so its narration text is kept there instead, truncated.
    adj1 = models.CharField(db_column="adj1", max_length=1, blank=True, null=True)
    adj_code1 = models.CharField("add/less 1 narration", db_column="adj_code1", max_length=4, blank=True, null=True)
    adj_rt1 = models.DecimalField(db_column="adj_rt1", max_digits=10, decimal_places=2, blank=True, null=True)
    adj_amt1 = models.DecimalField(db_column="adj_amt1", max_digits=12, decimal_places=2, blank=True, null=True)
    adj2 = models.CharField(db_column="adj2", max_length=1, blank=True, null=True)
    adj_code2 = models.CharField("add/less 2 narration", db_column="adj_code2", max_length=4, blank=True, null=True)
    adj_rt2 = models.DecimalField(db_column="adj_rt2", max_digits=10, decimal_places=2, blank=True, null=True)
    adj_amt2 = models.DecimalField(db_column="adj_amt2", max_digits=12, decimal_places=2, blank=True, null=True)

    amt_tf = models.DecimalField("taxable @0%", db_column="amt_tf", max_digits=12, decimal_places=2, blank=True, null=True)
    amt5 = models.DecimalField("taxable @5%", db_column="amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    amt12 = models.DecimalField("taxable @12%", db_column="amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    amt18 = models.DecimalField("taxable @18%", db_column="amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    amt28 = models.DecimalField("taxable @28%", db_column="amt28", max_digits=12, decimal_places=2, blank=True, null=True)

    cg_rt5 = models.DecimalField(db_column="cg_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    cg_amt5 = models.DecimalField(db_column="cg_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_rt5 = models.DecimalField(db_column="sg_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    sg_amt5 = models.DecimalField(db_column="sg_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_rt12 = models.DecimalField(db_column="cg_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    cg_amt12 = models.DecimalField(db_column="cg_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_rt12 = models.DecimalField(db_column="sg_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    sg_amt12 = models.DecimalField(db_column="sg_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_rt18 = models.DecimalField(db_column="cg_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    cg_amt18 = models.DecimalField(db_column="cg_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_rt18 = models.DecimalField(db_column="sg_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    sg_amt18 = models.DecimalField(db_column="sg_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_rt28 = models.DecimalField(db_column="cg_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    cg_amt28 = models.DecimalField(db_column="cg_amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_rt28 = models.DecimalField(db_column="sg_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    sg_amt28 = models.DecimalField(db_column="sg_amt28", max_digits=12, decimal_places=2, blank=True, null=True)

    ig_rt5 = models.DecimalField(db_column="ig_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    ig_amt5 = models.DecimalField(db_column="ig_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_rt12 = models.DecimalField(db_column="ig_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    ig_amt12 = models.DecimalField(db_column="ig_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_rt18 = models.DecimalField(db_column="ig_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    ig_amt18 = models.DecimalField(db_column="ig_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_rt28 = models.DecimalField(db_column="ig_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    ig_amt28 = models.DecimalField(db_column="ig_amt28", max_digits=12, decimal_places=2, blank=True, null=True)

    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "c_bill"
        verbose_name = "GST credit note"
        verbose_name_plural = "GST credit notes"
        permissions = [("change_creditnote", "Can add, modify or delete a GST credit note")]

    def __str__(self):
        return f"Credit Note {self.bill_no or ''}".strip()


class GMasterCreditLine(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    bill_no = models.CharField(db_column="bill_no", max_length=5, blank=True, null=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    bill_type = models.CharField(db_column="bill_type", max_length=1, blank=True, null=True)
    line_date = models.DateField(db_column="date", blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    item_code = models.CharField(db_column="i_code", max_length=10, blank=True, null=True)
    item_name = models.CharField(db_column="prt_name", max_length=100, blank=True, null=True)
    hsn_code = models.CharField(db_column="hs_code", max_length=8, blank=True, null=True)
    unit = models.CharField(db_column="unit", max_length=3, blank=True, null=True)
    qty = models.DecimalField(db_column="qty", max_digits=12, decimal_places=3, blank=True, null=True)
    rate = models.DecimalField(db_column="rate", max_digits=12, decimal_places=2, blank=True, null=True)
    dis = models.DecimalField("dis %", db_column="dis", max_digits=5, decimal_places=2, blank=True, null=True)
    dis_amt = models.DecimalField(db_column="dis_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    amount = models.DecimalField(db_column="amount", max_digits=12, decimal_places=2, blank=True, null=True)
    gst = models.DecimalField("GST %", db_column="gst", max_digits=5, decimal_places=2, blank=True, null=True)
    gst_amt = models.DecimalField(db_column="gst_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    cgst_rt = models.DecimalField(db_column="cgst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    cgst_amt = models.DecimalField(db_column="cgst_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_rt = models.DecimalField(db_column="sgst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    sgst_amt = models.DecimalField(db_column="sgst_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    igst_rt = models.DecimalField(db_column="igst_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    igst_amt = models.DecimalField(db_column="igst_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    sno = models.DecimalField(db_column="sno", max_digits=6, decimal_places=0, blank=True, null=True)
    stts = models.CharField(db_column="stts", max_length=1, blank=True, null=True)
    cstat = models.CharField(db_column="cstat", max_length=1, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "g_master"
        verbose_name = "GST credit note line"


from .narration_models import CBillHeader  # noqa: E402,F401

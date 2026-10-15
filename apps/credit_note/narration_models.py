"""GST Credit Note (Narration) -- VFP "gcnar1" form, rate-wise (not item-wise).

The SAME physical table as the Spear Part variant (models.GcBillHeader) --
both are ``c_bill``, told apart by ``bill_type``: 'C' there, ' ' (a single
blank space) here, per the real VFP filter. Column mapping confirmed against
the live c_bill schema and the real rpldata/showdata/deldata VFP source for
this specific form.

Deliberately NOT done here (scope agreed with the user 2026-10-08): the
double-entry ledger postings rpldata also makes into ``trans`` (GST-rate-
bucket debits, Add/Less, the rounding-difference entry, and the final
customer credit) -- one of those entries needs a ledger account code
(the VFP global ``pdiffcode``) that isn't available yet. Only the document
header itself (what this screen's own grid needs) is kept here.
"""
from django.db import models


class CBillHeader(models.Model):
    bill_no = models.CharField("C.N. no", db_column="bill_no", max_length=5, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    vou_no = models.CharField(db_column="vou_no", max_length=5, blank=True, null=True)
    b_date = models.DateField("C.N. date", db_column="b_date", blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    bill_type = models.CharField(db_column="bill_type", max_length=1, blank=True, null=True)

    ag_bill = models.CharField("invoice no", db_column="ag_bill", max_length=20, blank=True, null=True)
    ag_date = models.DateField("invoice date", db_column="ag_date", blank=True, null=True)
    p_sup = models.CharField("place of supply", db_column="p_sup", max_length=20, blank=True, null=True)
    pre1 = models.CharField("pre-GST", db_column="pre1", max_length=1, blank=True, null=True)

    nar1 = models.CharField(db_column="nar1", max_length=30, blank=True, null=True)
    nar2 = models.CharField(db_column="nar2", max_length=30, blank=True, null=True)
    nar3 = models.CharField(db_column="nar3", max_length=30, blank=True, null=True)
    nar4 = models.CharField(db_column="nar4", max_length=30, blank=True, null=True)

    # Rate-wise taxable value + GST, one group of columns per slab -- same
    # camt/gdis/amt{r}/cg_amt{r}/sg_amt{r}/ig_amt{r} columns the Spear Part
    # form's legacy header (models.GcBillHeader) also has, but on this table.
    camt0 = models.DecimalField("taxable @0% (before dis)", db_column="camt0", max_digits=12, decimal_places=2, blank=True, null=True)
    gdis0 = models.DecimalField("dis % @0%", db_column="gdis0", max_digits=5, decimal_places=2, blank=True, null=True)
    amt_tf = models.DecimalField("taxable @0%", db_column="amt_tf", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_am0 = models.DecimalField(db_column="ig_am0", max_digits=12, decimal_places=2, blank=True, null=True)

    camt5 = models.DecimalField("taxable @5% (before dis)", db_column="camt5", max_digits=12, decimal_places=2, blank=True, null=True)
    gdis5 = models.DecimalField("dis % @5%", db_column="gdis5", max_digits=5, decimal_places=2, blank=True, null=True)
    amt5 = models.DecimalField("taxable @5%", db_column="amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_amt5 = models.DecimalField(db_column="cg_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_amt5 = models.DecimalField(db_column="sg_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_amt5 = models.DecimalField(db_column="ig_amt5", max_digits=12, decimal_places=2, blank=True, null=True)

    camt12 = models.DecimalField("taxable @12% (before dis)", db_column="camt12", max_digits=12, decimal_places=2, blank=True, null=True)
    gdis12 = models.DecimalField("dis % @12%", db_column="gdis12", max_digits=5, decimal_places=2, blank=True, null=True)
    amt12 = models.DecimalField("taxable @12%", db_column="amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_amt12 = models.DecimalField(db_column="cg_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_amt12 = models.DecimalField(db_column="sg_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_amt12 = models.DecimalField(db_column="ig_amt12", max_digits=12, decimal_places=2, blank=True, null=True)

    camt18 = models.DecimalField("taxable @18% (before dis)", db_column="camt18", max_digits=12, decimal_places=2, blank=True, null=True)
    gdis18 = models.DecimalField("dis % @18%", db_column="gdis18", max_digits=5, decimal_places=2, blank=True, null=True)
    amt18 = models.DecimalField("taxable @18%", db_column="amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_amt18 = models.DecimalField(db_column="cg_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_amt18 = models.DecimalField(db_column="sg_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_amt18 = models.DecimalField(db_column="ig_amt18", max_digits=12, decimal_places=2, blank=True, null=True)

    camt28 = models.DecimalField("taxable @28% (before dis)", db_column="camt28", max_digits=12, decimal_places=2, blank=True, null=True)
    gdis28 = models.DecimalField("dis % @28%", db_column="gdis28", max_digits=5, decimal_places=2, blank=True, null=True)
    amt28 = models.DecimalField("taxable @28%", db_column="amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    cg_amt28 = models.DecimalField(db_column="cg_amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    sg_amt28 = models.DecimalField(db_column="sg_amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    ig_amt28 = models.DecimalField(db_column="ig_amt28", max_digits=12, decimal_places=2, blank=True, null=True)

    amount = models.DecimalField("total taxable amount", db_column="amount", max_digits=12, decimal_places=2, blank=True, null=True)
    gst_amt = models.DecimalField("total GST", db_column="gst_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    # c_bill has cess_amt1 (the amount entered on screen) and cess_rt (a cess %
    # the real caltotal multiplies it by) but no separate "final cess amount"
    # column -- that was only ever a form-local variable (.tgcess) in the VFP
    # source, never persisted. cess_rt is always saved as 0 here since the Add
    # form has no visible rate input for it (only the one CESS AMOUNT box).
    cess_amt1 = models.DecimalField(db_column="cess_amt1", max_digits=12, decimal_places=2, blank=True, null=True)
    cess_rt = models.DecimalField(db_column="cess_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    diff_amt = models.DecimalField("rounding difference", db_column="diff_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    n_amount = models.DecimalField("net amount", db_column="n_amount", max_digits=12, decimal_places=2, blank=True, null=True)

    adj1 = models.CharField(db_column="adj1", max_length=1, blank=True, null=True)
    adj_code1 = models.CharField(db_column="adj_code1", max_length=4, blank=True, null=True)
    adj_rt1 = models.DecimalField(db_column="adj_rt1", max_digits=10, decimal_places=2, blank=True, null=True)
    adj_amt1 = models.DecimalField(db_column="adj_amt1", max_digits=12, decimal_places=2, blank=True, null=True)
    adj2 = models.CharField(db_column="adj2", max_length=1, blank=True, null=True)
    adj_code2 = models.CharField(db_column="adj_code2", max_length=4, blank=True, null=True)
    adj_rt2 = models.DecimalField(db_column="adj_rt2", max_digits=10, decimal_places=2, blank=True, null=True)
    adj_amt2 = models.DecimalField(db_column="adj_amt2", max_digits=12, decimal_places=2, blank=True, null=True)

    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "c_bill"
        verbose_name = "GST credit note (narration)"
        verbose_name_plural = "GST credit notes (narration)"
        permissions = [("change_creditnote_narration", "Can add, modify or delete a GST credit note (narration)")]

    def __str__(self):
        return f"Credit Note (Narration) {self.bill_no or ''}".strip()

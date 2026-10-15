"""d_bill -- the old software's purchase-side GST debit note header (VFP GST DEBIT NOTE
form). Posted alongside the Django-side DebitNote record when a debit note is saved, so
the legacy SQL Server data matches what the old VFP screen would have written.

Deliberately NOT included here: the ledger (trans) postings the VFP rpldata routine also
makes. Those use several sales-ledger account codes (per GST rate, their IGST variants,
and a rounding-difference code) that exist nowhere in this project's data or on this
form; guessing them would risk posting wrong journal entries into a live accounting
ledger, so that part is left undone pending those account codes.
"""
from django.db import models


class DebitNoteBill(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    bill_no = models.CharField("invoice no", db_column="bill_no", max_length=10, blank=True, null=True)
    bill_date = models.DateField("invoice date", db_column="b_date", blank=True, null=True)
    party_code = models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    amount = models.DecimalField(db_column="amount", max_digits=12, decimal_places=2, blank=True, null=True)
    net_amount = models.DecimalField(db_column="n_amount", max_digits=12, decimal_places=2, blank=True, null=True)
    gr_no = models.CharField(db_column="gr_no", max_length=20, blank=True, null=True)
    gr_date = models.DateField(db_column="gr_dt", blank=True, null=True)
    transport = models.CharField(db_column="trans", max_length=40, blank=True, null=True)
    grn_no = models.CharField("debit note no", db_column="grn_no", max_length=10, blank=True, null=True)
    grn_date = models.DateField("debit note date", db_column="grn_dt", blank=True, null=True)
    ag_pur = models.CharField(db_column="ag_pur", max_length=20, blank=True, null=True)
    ag_date = models.DateField(db_column="ag_date", blank=True, null=True)
    date = models.DateField(db_column="date", blank=True, null=True)
    dis_amt = models.DecimalField(db_column="dis_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    gst_amt = models.DecimalField(db_column="gst_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    po_no = models.CharField(db_column="po_no", max_length=20, blank=True, null=True)
    po_date = models.DateField(db_column="po_dt", blank=True, null=True)
    cstat = models.CharField(db_column="cstat", max_length=2, blank=True, null=True)
    pur_type = models.CharField(db_column="pur_type", max_length=2, blank=True, null=True)
    freight_rate = models.DecimalField(db_column="fr_rt", max_digits=5, decimal_places=2, blank=True, null=True)
    freight_amount = models.DecimalField(db_column="fr_amt", max_digits=12, decimal_places=2, blank=True, null=True)
    freight_gst_amount = models.DecimalField(db_column="fr_amt1", max_digits=12, decimal_places=2, blank=True, null=True)

    taxable_0 = models.DecimalField(db_column="amt_tf", max_digits=12, decimal_places=2, blank=True, null=True)
    taxable_5 = models.DecimalField(db_column="amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    taxable_12 = models.DecimalField(db_column="amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    taxable_18 = models.DecimalField(db_column="amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    taxable_28 = models.DecimalField(db_column="amt28", max_digits=12, decimal_places=2, blank=True, null=True)

    # Mirror columns the old form also fills with the same taxable values.
    purch_0 = models.DecimalField(db_column="gpur0", max_digits=12, decimal_places=2, blank=True, null=True)
    purch_5 = models.DecimalField(db_column="gpur5", max_digits=12, decimal_places=2, blank=True, null=True)
    purch_12 = models.DecimalField(db_column="gpur12", max_digits=12, decimal_places=2, blank=True, null=True)
    purch_18 = models.DecimalField(db_column="gpur18", max_digits=12, decimal_places=2, blank=True, null=True)
    purch_28 = models.DecimalField(db_column="gpur28", max_digits=12, decimal_places=2, blank=True, null=True)
    taxable_0_alt = models.DecimalField(db_column="t_val0", max_digits=12, decimal_places=2, blank=True, null=True)

    cgst_rt5 = models.DecimalField(db_column="cg_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    cgst_amt5 = models.DecimalField(db_column="cg_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_rt5 = models.DecimalField(db_column="sg_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    sgst_amt5 = models.DecimalField(db_column="sg_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    cgst_rt12 = models.DecimalField(db_column="cg_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    cgst_amt12 = models.DecimalField(db_column="cg_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_rt12 = models.DecimalField(db_column="sg_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    sgst_amt12 = models.DecimalField(db_column="sg_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    cgst_rt18 = models.DecimalField(db_column="cg_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    cgst_amt18 = models.DecimalField(db_column="cg_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_rt18 = models.DecimalField(db_column="sg_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    sgst_amt18 = models.DecimalField(db_column="sg_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    cgst_rt28 = models.DecimalField(db_column="cg_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    cgst_amt28 = models.DecimalField(db_column="cg_amt28", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_rt28 = models.DecimalField(db_column="sg_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    sgst_amt28 = models.DecimalField(db_column="sg_amt28", max_digits=12, decimal_places=2, blank=True, null=True)

    # Mirror columns the old form also fills with the same CGST / SGST amounts.
    cgst_am5 = models.DecimalField(db_column="cgst_am5", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_am5 = models.DecimalField(db_column="sgst_am5", max_digits=12, decimal_places=2, blank=True, null=True)
    cgst_am12 = models.DecimalField(db_column="cgst_am12", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_am12 = models.DecimalField(db_column="sgst_am12", max_digits=12, decimal_places=2, blank=True, null=True)
    cgst_am18 = models.DecimalField(db_column="cgst_am18", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_am18 = models.DecimalField(db_column="sgst_am18", max_digits=12, decimal_places=2, blank=True, null=True)
    cgst_am28 = models.DecimalField(db_column="cgst_am28", max_digits=12, decimal_places=2, blank=True, null=True)
    sgst_am28 = models.DecimalField(db_column="sgst_am28", max_digits=12, decimal_places=2, blank=True, null=True)

    igst_rt5 = models.DecimalField(db_column="ig_rt5", max_digits=5, decimal_places=2, blank=True, null=True)
    igst_amt5 = models.DecimalField(db_column="ig_amt5", max_digits=12, decimal_places=2, blank=True, null=True)
    igst_rt12 = models.DecimalField(db_column="ig_rt12", max_digits=5, decimal_places=2, blank=True, null=True)
    igst_amt12 = models.DecimalField(db_column="ig_amt12", max_digits=12, decimal_places=2, blank=True, null=True)
    igst_rt18 = models.DecimalField(db_column="ig_rt18", max_digits=5, decimal_places=2, blank=True, null=True)
    igst_amt18 = models.DecimalField(db_column="ig_amt18", max_digits=12, decimal_places=2, blank=True, null=True)
    igst_rt28 = models.DecimalField(db_column="ig_rt28", max_digits=5, decimal_places=2, blank=True, null=True)
    igst_amt28 = models.DecimalField(db_column="ig_amt28", max_digits=12, decimal_places=2, blank=True, null=True)

    # Mirror columns the old form also fills with the same IGST amounts.
    igst_am5 = models.DecimalField(db_column="igst_am5", max_digits=12, decimal_places=2, blank=True, null=True)
    igst_am12 = models.DecimalField(db_column="igst_am12", max_digits=12, decimal_places=2, blank=True, null=True)
    igst_am18 = models.DecimalField(db_column="igst_am18", max_digits=12, decimal_places=2, blank=True, null=True)
    igst_am28 = models.DecimalField(db_column="igst_am28", max_digits=12, decimal_places=2, blank=True, null=True)

    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "d_bill"
        verbose_name = "GST debit note (legacy)"
        verbose_name_plural = "GST debit notes (legacy)"

    def __str__(self):
        return f"Debit Note {self.grn_no or ''}".strip()

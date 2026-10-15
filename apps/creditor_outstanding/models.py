# Creditor Outstanding has no table of its own. The old software's bill table
# (apps.outstanding.models.Bill) already holds outstanding invoices for BOTH
# ledger groups -- Sundry Debtors (party group S001, shown in Previous
# Outstanding) and Sundry Creditors (party group S002, shown here). This
# module is a thin, creditor-only layer over that same table and model, so
# Previous Outstanding, Creditor Outstanding and the database always agree
# on the same rows; see apps/creditor_outstanding/services.py.


from django.db import models as _models  # noqa: E402


class CreditorBill(_models.Model):
    """cr_out -- creditor bills the VFP payment entry settles."""

    id = _models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    div = _models.CharField(db_column="div", max_length=2, blank=True, null=True)
    inv_no = _models.CharField(db_column="inv_no", max_length=10, blank=True, null=True)
    inv_dt = _models.DateField(db_column="inv_dt", blank=True, null=True)
    p_code = _models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    amount = _models.DecimalField(db_column="amount", max_digits=10, decimal_places=2, blank=True, null=True)
    dr_amt = _models.DecimalField(db_column="dr_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    tds_amt = _models.DecimalField(db_column="tds_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    pmt_rcd = _models.DecimalField(db_column="pmt_rcd", max_digits=10, decimal_places=2, blank=True, null=True)
    c_dis = _models.DecimalField(db_column="c_dis", max_digits=10, decimal_places=2, blank=True, null=True)
    int_amt = _models.DecimalField(db_column="int_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    pmt_mad = _models.CharField(db_column="pmt_mad", max_length=1, blank=True, null=True)
    nar = _models.CharField(db_column="nar", max_length=20, blank=True, null=True)
    mrn_no = _models.CharField(db_column="mrn_no", max_length=10, blank=True, null=True)
    cl_date = _models.DateField(db_column="cl_date", blank=True, null=True)
    uname = _models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "cr_out"


class PaymentDetail(_models.Model):
    """p_col -- one row per bill settled by a payment."""

    id = _models.BigAutoField(primary_key=True)
    div = _models.CharField(db_column="div", max_length=2, blank=True, null=True)
    bill_no = _models.CharField(db_column="bill_no", max_length=10, blank=True, null=True)
    b_date = _models.DateField(db_column="b_date", blank=True, null=True)
    b_amt = _models.DecimalField(db_column="b_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    p_code = _models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    amount = _models.DecimalField(db_column="amount", max_digits=10, decimal_places=2, blank=True, null=True)
    c_dis = _models.DecimalField(db_column="c_dis", max_digits=10, decimal_places=2, blank=True, null=True)
    int_amt = _models.DecimalField(db_column="int_amt", max_digits=10, decimal_places=2, blank=True, null=True)
    nar = _models.CharField(db_column="nar", max_length=20, blank=True, null=True)
    date = _models.DateField(db_column="date", blank=True, null=True)
    remk = _models.CharField(db_column="remk", max_length=40, blank=True, null=True)
    uname = _models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "p_col"


class LedgerVoucher(_models.Model):
    """trans -- ledger postings made by a payment (JV / CV vouchers)."""

    id = _models.BigAutoField(primary_key=True)
    ttype = _models.CharField(db_column="ttype", max_length=2, blank=True, null=True)
    tdoc = _models.DecimalField(db_column="tdoc", max_digits=10, decimal_places=0, blank=True, null=True)
    tdate = _models.DateField(db_column="tdate", blank=True, null=True)
    tcode = _models.CharField(db_column="tcode", max_length=6, blank=True, null=True)
    tccode = _models.CharField(db_column="tccode", max_length=6, blank=True, null=True)
    tdbcr = _models.CharField(db_column="tdbcr", max_length=1, blank=True, null=True)
    tnar1 = _models.CharField(db_column="tnar1", max_length=40, blank=True, null=True)
    tnar2 = _models.CharField(db_column="tnar2", max_length=40, blank=True, null=True)
    tamt = _models.DecimalField(db_column="tamt", max_digits=12, decimal_places=2, blank=True, null=True)
    nar = _models.CharField(db_column="nar", max_length=20, blank=True, null=True)
    p_code = _models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    div = _models.CharField(db_column="div", max_length=2, blank=True, null=True)
    uname = _models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "trans"


class VoucherCounter(_models.Model):
    """vno -- JV / CV voucher numbers, one row per date."""

    id = _models.BigAutoField(primary_key=True)
    date = _models.DateField(db_column="date", blank=True, null=True)
    cvvno = _models.DecimalField(db_column="cvvno", max_digits=10, decimal_places=0, blank=True, null=True)
    jvvno = _models.DecimalField(db_column="jvvno", max_digits=10, decimal_places=0, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "vno"


class AdvanceFile(_models.Model):
    """adv_fil -- advance paid to a vendor, reduced by advance adjustments."""

    id = _models.BigAutoField(primary_key=True)
    p_code = _models.CharField(db_column="p_code", max_length=4, blank=True, null=True)
    amount = _models.DecimalField(db_column="amount", max_digits=10, decimal_places=2, blank=True, null=True)
    uname = _models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "adv_fil"

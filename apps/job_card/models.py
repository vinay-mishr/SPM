"""
Job Card -- legacy VFP JOB ENTRY (new_job + imaster 'S'/'P' lines + stock).
All tables are managed by the legacy system; Django never writes their schema.
"""
from django.db import models


class InvNo(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    next_jc_no = models.DecimalField(db_column="sp_jc_no", max_digits=10, decimal_places=0, null=True)

    class Meta:
        managed = False
        db_table = "inv_no"
        verbose_name = "document numbering counter"


class JobCard(models.Model):
    job_no = models.CharField("job no", db_column="job_no", max_length=9, primary_key=True)
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    job_date = models.DateField("job date", db_column="date", blank=True, null=True)
    item_code = models.CharField("product", db_column="i_code", max_length=10, blank=True, null=True)
    qty = models.DecimalField("job qty", db_column="qty", max_digits=10, decimal_places=0, blank=True, null=True)
    received = models.DecimalField("received", db_column="product", max_digits=6, decimal_places=0, blank=True, null=True)
    received_qty = models.DecimalField("rec qty", db_column="product1", max_digits=10, decimal_places=3, blank=True, null=True)
    waste = models.DecimalField("net weight", db_column="net_west", max_digits=5, decimal_places=0, blank=True, null=True)
    close_flag = models.CharField("closed", db_column="close", max_length=1, blank=True, null=True)
    close_date = models.DateField("close date", db_column="cl_date", blank=True, null=True)
    sub_assembly = models.CharField(db_column="sub", max_length=1, blank=True, null=True)
    supervisor = models.CharField("supervisor", db_column="sp_code", max_length=4, blank=True, null=True)
    start_date = models.DateField("start date", db_column="st_date", blank=True, null=True)
    time_taken = models.DecimalField("time taken", db_column="time_taken", max_digits=5, decimal_places=2, blank=True, null=True)
    issue_flag = models.CharField(db_column="iss", max_length=1, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "new_job"
        verbose_name = "job card"

    def __str__(self):
        return f"Job {self.job_no}"


class JobLine(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; imaster has no key
    div = models.CharField(db_column="div", max_length=2, blank=True, null=True)
    line_date = models.DateField(db_column="date", blank=True, null=True)
    part_code = models.CharField(db_column="i_code", max_length=10, blank=True, null=True)
    qty = models.DecimalField(db_column="qty", max_digits=12, decimal_places=3, blank=True, null=True)
    status = models.CharField(db_column="stts", max_length=1, blank=True, null=True)  # S = issued, P = received
    job_no = models.CharField(db_column="job_no", max_length=9, blank=True, null=True)
    item_code = models.CharField(db_column="item", max_length=10, blank=True, null=True)
    batch_no = models.CharField(db_column="b_no", max_length=9, blank=True, null=True)
    serial_no = models.CharField("serial no", db_column="jo_no", max_length=9, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "imaster"
        verbose_name = "job line"


class StockBalance(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; the stock table has no key
    item_code = models.CharField(db_column="i_code", max_length=10, blank=True, null=True)
    stock = models.DecimalField(db_column="stock", max_digits=10, decimal_places=0, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "stock"
        verbose_name = "sub-assembly stock"

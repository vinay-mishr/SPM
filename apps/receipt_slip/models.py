"""
Single Receipt Slip -- old VFP form "SINGLE RECEIPT SLIP" / form file "rmis1".

* ``ReceiptSlip`` is the existing ``rmis_mst`` table (header). ``managed = False``.
* ``InvNo`` maps the receipt counter ``inv_no.rmis_no`` on the shared counter row.
* Line items are ``imaster`` rows with ``bill_no`` = receipt challan, ``stts='R'``
  and ``recv='Y'`` -- see apps.purchase_orders.models.ItemMasterTransaction and
  services.py for the confirmed legacy save rules (raw source: D:/SPM/rmis1.SCT).
"""
from django.db import models


class InvNo(models.Model):
    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    next_receipt_no = models.DecimalField(db_column="rmis_no", max_digits=10, decimal_places=0)

    class Meta:
        managed = False
        db_table = "inv_no"
        verbose_name = "document numbering counter"


class ReceiptSlip(models.Model):
    mis_no = models.CharField("challan no", db_column="mis_no", max_length=6, primary_key=True)
    mis_date = models.DateField("date", db_column="mis_dt", blank=True, null=True)
    remarks = models.CharField(db_column="remk", max_length=40, blank=True, null=True)
    remarks1 = models.CharField(db_column="remk1", max_length=40, blank=True, null=True)
    ttype = models.CharField(db_column="ttype", max_length=1, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "rmis_mst"
        ordering = ["-mis_date", "-mis_no"]
        verbose_name = "receipt slip"
        verbose_name_plural = "receipt slips"
        permissions = [("change_receipt_slip", "Can add, modify or delete a Single Receipt Slip")]

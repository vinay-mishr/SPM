"""
Single Issue Slip — old VFP form "SINGLE ISSUE SLIP" / form file "mis1".

* ``IssueSlip`` is the existing ``mis_mst`` table -- one row per issue slip
  (the party/department it's issued to isn't tracked by this table at all;
  only the challan no, date, type flag and remarks are). ``managed = False``:
  Django never creates, alters or drops it. The table has 0 rows in this
  environment as of writing -- a genuinely unused-so-far legacy screen, not a
  sign the mapping is wrong (see the module's own notes in services.py).

* Line items live in the existing ``imaster`` table (``apps.purchase_orders.
  models.ItemMasterTransaction``), same shared table MRN Entry's items live
  in. Single Issue Slip lines are the rows with ``bill_no`` = challan no,
  ``sing = 'Y'`` and ``stts = 'I'`` (confirmed against the legacy save code in
  the legacy files D:/SPM/mis1.SCT and rrmis1.SCT).
"""
from django.db import models


class InvNo(models.Model):
    """
    The old software's shared numbering-counter row (``inv_no``) -- same single
    row ``apps.mrn.models.InvNo`` maps ``sp_mrn_no`` from, just this screen's
    own counter column (``mis_no``) instead. Only that one column is mapped,
    same convention as the MRN module's own copy of this table.
    """

    id = models.BigAutoField(primary_key=True)  # surrogate; the real table has no key
    next_issue_no = models.DecimalField(db_column="mis_no", max_digits=10, decimal_places=0)

    class Meta:
        managed = False
        db_table = "inv_no"
        verbose_name = "document numbering counter"


class IssueSlip(models.Model):
    """
    Issue slip header -- the existing ``mis_mst`` table. ``dept_code``,
    ``gcode``, ``div_code``, ``div_name``, ``type``, ``gr_no``, ``gr_dt``,
    ``lr_no``, ``rtn_no``, ``purpose`` and ``remk1`` exist on the real table
    but aren't shown anywhere on the reference screenshots this module was
    built from, so -- same convention as this project's other legacy tables --
    they're left unmapped rather than guessed.
    """

    # mis_no as the Django primary key (not a surrogate "id") -- same convention
    # as MrnData.mrn_no: the table has no real key of its own, but using an
    # actually-existing column instead of an invented one means model instances
    # (.save()/.delete()/.first()) work without Django trying to SELECT a
    # column that doesn't exist.
    mis_no = models.CharField("challan no", db_column="mis_no", max_length=6, primary_key=True)
    mis_date = models.DateField("date", db_column="mis_dt", blank=True, null=True)
    remarks = models.CharField(db_column="remk", max_length=40, blank=True, null=True)
    # The legacy listing's own filter is "AND TTYPE=' '" -- a real, if currently
    # always-blank, discriminator column (other TTYPE values presumably mark a
    # different old screen's rows in the same table); always written as a
    # single space on save, matching that filter literally.
    ttype = models.CharField(db_column="ttype", max_length=1, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "mis_mst"
        ordering = ["-mis_date", "-mis_no"]
        verbose_name = "issue slip"
        verbose_name_plural = "issue slips"
        permissions = [("change_issue_slip", "Can add, modify or delete a Single Issue Slip")]

    def __str__(self):
        return self.mis_no

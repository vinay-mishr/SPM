from django.db import models


class BomComponent(models.Model):
    """
    Bill of Material line — the existing ``con-mst`` table of the old software
    (SP_MACHINE). Old VFP form: BILL OF MATERIAL MASTER.

    Each row says: to build one PART (``part_code``, a part-mst row, e.g.
    "ABM01" INFEED ASSY), ``qty`` of one ITEM (``item_code``, an item-master
    row) is consumed. The screen labels these "Item Name" (the part being
    built) and "Part Description" (the item consumed) -- the old software's
    own naming, kept here only as help text; the real columns are unambiguous.

    ``managed = False``: Django never creates, alters or drops this table.
    The table has no key at all -- not even (part_code, item_code) is unique,
    a handful of real rows repeat exactly. Saving therefore always replaces
    *all* rows for one part_code in a single transaction (delete + re-insert)
    rather than updating an individual row; see apps/bom/services.py.
    """

    part_code = models.CharField(
        "part code", db_column="icod", max_length=10, primary_key=True,
        help_text="The part being built (part-mst); shown as “Item Name” on the old screen.",
    )
    item_code = models.CharField(
        "item code", db_column="item", max_length=10, blank=True, null=True,
        help_text="The item consumed (item master); shown as “Part Description” on the old screen.",
    )
    quantity = models.DecimalField(db_column="qty", max_digits=12, decimal_places=5, blank=True, null=True)
    unit = models.CharField(db_column="unit", max_length=3, blank=True, null=True)  # widened from varchar(2) to match conms.unit
    time_required = models.DecimalField("time required", db_column="time_req", max_digits=10, decimal_places=2, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "con-mst"
        ordering = ["part_code", "item_code"]
        verbose_name = "bill of material line"
        verbose_name_plural = "bill of material lines"
        permissions = [("change_bom", "Can change bill of material")]

    def __str__(self):
        return f"{self.part_code} / {self.item_code or ''}".strip()


class BomSaComponent(models.Model):
    """
    Bill of Material Master (Sub Assembly) line -- the old software's ``conms``
    table (a *different*, separate physical table from ``con-mst`` above; the
    old VFP code opens it explicitly as ``use conms``). Old VFP form: BILL OF
    MATERIAL MASTER (SUB ASSEMBLY).

    Each row says: to build one PART (``parent_part_code``, e.g. "ABM01"
    INFEED ASSY), ``qty`` of one component PART (``component_part_code``,
    e.g. "ABM01_001" FLAT) is needed -- both sides are part-mst rows. This
    was confirmed against a real reference screenshot and by querying the
    live ``conms`` table directly. ``icod`` holds the CHILD/component code
    here and ``item`` holds the PARENT code -- the reverse of ``con-mst``'s
    convention, and the old screen's "ITEM NAME" label for the parent field
    is the old software's own naming, not a hint that it is an item-master
    code.

    ``managed = False``: Django never creates, alters or drops this table.
    Like ``con-mst``, the table has no key -- saving therefore always
    replaces *all* rows for one parent part_code in a single transaction.
    """

    component_part_code = models.CharField(
        "component part code", db_column="icod", max_length=10, primary_key=True,
        help_text="The component consumed (part-mst); shown as “Part Description” on the old screen.",
    )
    parent_part_code = models.CharField(
        "parent part code", db_column="item", max_length=10, blank=True, null=True,
        help_text="The part being built (part-mst); shown as “Item Name” on the old screen.",
    )
    quantity = models.DecimalField(db_column="qty", max_digits=12, decimal_places=5, blank=True, null=True)
    unit = models.CharField(
        db_column="unit", max_length=3, blank=True, null=True,
        help_text="Widened from varchar(2) to varchar(3) to match part-mst.uom exactly (PCS, SET, BOX, ...).",
    )
    time_required = models.DecimalField("time required", db_column="time_req", max_digits=10, decimal_places=2, blank=True, null=True)
    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "conms"
        ordering = ["parent_part_code", "component_part_code"]
        verbose_name = "bill of material (sub assembly) line"
        verbose_name_plural = "bill of material (sub assembly) lines"

    def __str__(self):
        return f"{self.parent_part_code} / {self.component_part_code or ''}".strip()

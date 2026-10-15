from django.db import models


class Part(models.Model):
    """
    Part / BOM item — the existing ``part-mst`` table of the old software (SP_MACHINE).
    The old grid's title reads "(RAW MATERIAL)"; it holds every raw material,
    component, consumable and sub-assembly used to build a machine.

    ``managed = False``: Django never creates, alters or drops this table. The table
    has no key of its own; ``icod`` (the part number, e.g. "ABM01_003") is unique
    for almost all rows and is used as the key. A handful of very old rows share a
    part number (see ``services.duplicate_part_numbers``); those are protected from
    MODIFY/DELETE here so the wrong row is never touched.

    Columns not listed here (p_order, uom-related codes, div1-3, mst_pc, inv_rt,
    dummy_stk, conv, e_lot, old_rt, rps, ayn, ws, routine, labour, chk, dum_stk,
    grade1-4, gopstk, order, ppath) are left untouched.
    """

    part_number = models.CharField("part no", db_column="icod", max_length=10, primary_key=True)
    description_1 = models.CharField("part description", db_column="ides", max_length=35, blank=True, null=True)
    description_2 = models.CharField("part description 2", db_column="rname1", max_length=35, blank=True, null=True)
    quantity_in_order = models.DecimalField("qty in order", db_column="qnty", max_digits=11, decimal_places=3, blank=True, null=True)
    drawing_no = models.CharField("drawing no", db_column="drgno", max_length=10, blank=True, null=True)
    gauge = models.CharField(db_column="gauge", max_length=10, blank=True, null=True)
    packing = models.DecimalField(db_column="std_pack", max_digits=5, decimal_places=0, blank=True, null=True)
    grade = models.CharField(db_column="grade", max_length=2, blank=True, null=True)
    gross_weight = models.DecimalField(db_column="g_wt", max_digits=10, decimal_places=4, blank=True, null=True)

    purchase_rate = models.DecimalField("pur. rate", db_column="rate", max_digits=10, decimal_places=4, blank=True, null=True)
    sale_rate = models.DecimalField(db_column="srate", max_digits=10, decimal_places=2, blank=True, null=True)
    opening_stock = models.DecimalField("op stock", db_column="op_stk", max_digits=12, decimal_places=3, blank=True, null=True)
    reorder_qty = models.DecimalField(db_column="rop", max_digits=11, decimal_places=3, blank=True, null=True)
    qty_on_order = models.DecimalField("qty on order", db_column="p_order1", max_digits=11, decimal_places=3, blank=True, null=True)
    material = models.CharField(db_column="material", max_length=15, blank=True, null=True)
    weight_by_100 = models.DecimalField("weight/100", db_column="wt", max_digits=7, decimal_places=3, blank=True, null=True)
    current_stock = models.DecimalField("current stk", db_column="cur_stk", max_digits=10, decimal_places=0, blank=True, null=True)
    # The stock balance the legacy Single Issue save reduces (and delete restores).
    # Distinct from current_stock (cur_stk), which the legacy code never touches here.
    stock_balance = models.DecimalField("stock", db_column="stock", max_digits=10, decimal_places=0, blank=True, null=True)
    planning_stock = models.DecimalField("planning stock", db_column="dummy_stk", max_digits=10, decimal_places=3, blank=True, null=True)
    conversion_flag = models.CharField("conversion (Y/N)", db_column="conv", max_length=2, blank=True, null=True)
    active_flag = models.CharField("active / NA (Y/N)", db_column="ayn", max_length=2, blank=True, null=True)
    routine_flag = models.CharField("routine (R/S)", db_column="routine", max_length=1, blank=True, null=True)
    workshop_flag = models.CharField("workshop (Y)", db_column="ws", max_length=1, blank=True, null=True)
    os_ih_flag = models.CharField("OS/IH", db_column="os_ih", max_length=1, blank=True, null=True)
    location = models.CharField(db_column="loc", max_length=10, blank=True, null=True)
    unit = models.CharField(db_column="uom", max_length=3, blank=True, null=True)
    hsn_code = models.CharField("HSN code", db_column="hs_code", max_length=8, blank=True, null=True)
    gst_percent = models.DecimalField("GST %", db_column="gs_rt", max_digits=5, decimal_places=2, blank=True, null=True)

    sub_assembly = models.CharField(db_column="s_cod", max_length=1, blank=True, null=True)  # 'Y' / ''
    part_type = models.CharField(db_column="item_type", max_length=1, blank=True, null=True)  # '' / R / C / S

    supplier_1 = models.CharField(db_column="party1", max_length=4, blank=True, null=True)
    rate_1 = models.DecimalField(db_column="rate1", max_digits=10, decimal_places=4, blank=True, null=True)
    supplier_2 = models.CharField(db_column="party2", max_length=4, blank=True, null=True)
    rate_2 = models.DecimalField(db_column="rate2", max_digits=10, decimal_places=4, blank=True, null=True)
    supplier_3 = models.CharField(db_column="party3", max_length=4, blank=True, null=True)
    rate_3 = models.DecimalField(db_column="rate3", max_digits=10, decimal_places=4, blank=True, null=True)
    supplier_4 = models.CharField(db_column="party4", max_length=4, blank=True, null=True)
    rate_4 = models.DecimalField(db_column="rate4", max_digits=10, decimal_places=4, blank=True, null=True)

    uname = models.CharField(db_column="uname", max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "part-mst"
        ordering = ["part_number"]
        verbose_name = "part"
        verbose_name_plural = "parts"
        permissions = [("change_rate", "Can modify item rates (Rate Modification)")]

    def __str__(self):
        return f"{self.part_number} {self.description_1 or ''}".strip()

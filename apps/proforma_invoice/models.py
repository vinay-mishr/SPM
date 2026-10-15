# Proforma Invoice (old VFP form "gPER1", list "PERFORMA INVOICE") has no models of
# its own: header lives in the existing ``g_per`` table (``bill_type = 'G'``, its own
# numbering counter ``inv_no.gp_inv_no`` -- confirmed from the real VFP source, and
# NOT the same counter or table as apps.gst_invoice's 'G' bills), lines live in
# ``p_master``. Both are addressed with raw SQL in services.py (same convention as
# apps.gst_invoice / apps.spare_invoice) because of how many columns the real rows
# carry.
#
# Deliberately, per explicit instruction, this module NEVER posts to ``trans``
# (the shared ledger) and NEVER touches ``item.cur_stk`` or any stock/order table --
# a proforma is a quotation, not a finalized sale. The real VFP ``rpldata`` routine's
# entire ledger-posting section is itself commented out (``*!*``) in the source this
# was built from, confirming the legacy app already treats it this way.

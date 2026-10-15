# Spare Part Invoice (old VFP form "gstbill7", bill_type='P') has no models of its
# own: its header lives in the same ``bill`` table as apps.gst_invoice ('G' type),
# sharing the very same ``inv_no.gb_inv_no`` numbering counter (confirmed from the
# real VFP source: both forms run ``nn=allt(str(gb_inv_no+1))`` against the same
# column) -- so bill_no is unique across *both* bill types, never just within one.
# The handful of fields that have no column on ``bill`` (date/time/place of supply,
# e-way no/date, reverse charge) are the same gap apps.gst_invoice hit, so this app
# reuses apps.gst_invoice.models.GstInvoiceExtra directly rather than duplicating an
# identical side table keyed by the same (globally unique) bill_no.

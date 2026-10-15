# Vendor Master has no table of its own. The old software's Vendor Master
# (VFP form supfrm) is simply cust_mst filtered to the Sundry Creditor group
# (code = settings.PARTY_CREDITOR_CODE, "S002") -- the SAME real table and
# Django model Party Master already uses (apps.parties.models.Party). Vendor
# Master reads/writes through that one model so it, Party Master and the
# database always agree on the same records; see apps/vendors/services.py.

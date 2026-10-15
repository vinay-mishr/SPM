# Rate Modification has no table of its own. It reads and writes the existing
# part-mst (rate column only) through apps.parts.models.Part / apps.rate_modification.services,
# so Item Master, Part Master and this screen always agree on the same data.

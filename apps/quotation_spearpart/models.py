"""
Quotation (Spare Part) -- legacy VFP "QUOTATION" list and "QUOTATION HEAD" entry form
(form QUOT4, list filtered ``TYPE='Q'``).

This screen shares its tables with ``apps.quotations`` (the ``TYPE=' '`` blank-type
screen) rather than owning new ones:

* Header: the existing ``quot_mst`` table -- ``apps.quotations.models.QuotationHeader``
  (same Python model, reused directly; its docstring already documents that rows with
  ``type='Q'`` belong to this other legacy screen).
* Lines: the existing ``quot_dat`` table -- no key column, so no model; services.py
  reads/writes it with parameterised SQL, same as apps.quotations does.
* Numbering: the SAME shared counter, ``inv_no.quot_no`` (``apps.quotations.models.InvNo``)
  -- confirmed by the legacy source (QUOT4's ADD handler reads ``inv_no.quot_no + 1``,
  the very same field the blank-type screen's ADD handler uses) and by quot_mst.quot_no
  being that table's single primary key, shared by every row regardless of type.
* Audit / dedup: ``apps.quotations.models.QuotationMeta`` / ``QuotationSubmission``
  (``web_quot_audit`` / ``web_quot_submit``) are reused as-is -- they're keyed uniquely
  by quotation number, which is already unique across both screens, so no new tables
  are needed here.

Items come from ``part-mst`` (``apps.parts.models.Part``), not the ``item`` master the
blank-type screen uses -- confirmed by the legacy source's
``use part-mst in 0 order i_code alia partmst`` and its PARTHELP3 lookup form.

``quot_dat.i_code`` was ``varchar(4)`` in the live database -- too narrow for real part
numbers (confirmed up to 10 chars, e.g. "ABM01_001A"), and almost certainly why none of
the 13 real ``type='Q'`` quotations in the live data have any saved line items (users
quoted a lump sum instead). Widened to ``varchar(10)`` by
``manage.py widen_quot_dat_icode --apply`` (see that command) before this module went
live; see that file for the exact, additive ALTER COLUMN statement.
"""

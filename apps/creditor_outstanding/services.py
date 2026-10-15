"""
Creditor Outstanding logic (old VFP form's "CREDITOR OUTSTANDING" window). This is
the same real ``bill`` table Previous Outstanding uses (apps.outstanding.models.Bill),
filtered to Sundry Creditor parties (``settings.PARTY_CREDITOR_CODE`` / "S002") --
no new table, so Previous Outstanding and Creditor Outstanding always agree on the
same rows. Add / Modify / Delete reuse apps.outstanding.services' proven logic
(receipt protection, single-row safety checks), only narrowed to creditor parties.
"""
from django.conf import settings

from apps.outstanding import services as bill_services
from apps.outstanding.models import Bill
from apps.outstanding.services import (  # re-exported for the views/forms
    DEFAULT_DIV,
    OutstandingError,
    create as _base_create,
    delete as _base_delete,
    divisions,
    update as _base_update,
    writes_enabled,
)
from apps.parties.models import Party

PERMISSION = "outstanding.change_creditor_outstanding"


def _creditor_codes():
    return set(Party.objects.filter(group_code=settings.PARTY_CREDITOR_CODE).values_list("party_code", flat=True))


def _is_creditor(party_code):
    return bool(party_code) and Party.objects.filter(
        party_code=party_code, group_code=settings.PARTY_CREDITOR_CODE
    ).exists()


def list_bills(div=DEFAULT_DIV):
    """Creditor-only bills of one division ('' = all), sorted by date then invoice no."""
    codes = _creditor_codes()
    return [row for row in bill_services.list_bills(div) if row["party_code"] in codes]


def search_parties(term, limit=15):
    """Party Master lookup restricted to Sundry Creditors (for the PARTY field)."""
    term = (term or "").strip()
    qs = Party.objects.filter(group_code=settings.PARTY_CREDITOR_CODE)
    if term:
        qs = qs.filter(_code_or_name_filter(term))
    return [
        {"code": c, "name": (n or "").strip(), "city": (city or "").strip(), "mobile": (mobile or "").strip()}
        for c, n, city, mobile in qs.order_by("name").values_list("party_code", "name", "city", "mobile_1")[:limit]
    ]


def _code_or_name_filter(term):
    from django.db.models import Q
    return Q(party_code__istartswith=term) | Q(name__icontains=term)


def create(data, username=""):
    if not _is_creditor(data.get("party_code")):
        raise OutstandingError("Select a Sundry Creditor party (this screen is for creditor outstanding only).")
    return _base_create(data, username)


def update(key, data):
    if not _is_creditor(data.get("party_code")):
        raise OutstandingError("Select a Sundry Creditor party (this screen is for creditor outstanding only).")
    div, bill_no, party_code = key
    if not _is_creditor(party_code):
        raise OutstandingError("This entry does not belong to a Sundry Creditor and cannot be changed here.")
    return _base_update(key, data)


def delete(key):
    div, bill_no, party_code = key
    if not _is_creditor(party_code):
        raise OutstandingError("This entry does not belong to a Sundry Creditor and cannot be deleted here.")
    return _base_delete(key)

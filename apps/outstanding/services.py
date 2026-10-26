"""Previous Outstanding logic (old software's bill table). Views stay thin and call these."""
from django.conf import settings
from django.db import connections, transaction

from apps.parties.models import Party
from config.legacy import fill_blank_columns

from .models import Bill

PERMISSION = "outstanding.change_previous_outstanding"
DEFAULT_DIV = "OL"  # previous years


class OutstandingError(Exception):
    """A save / delete that must be refused, with a message for the user."""


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _db():
    return Bill.objects.db


def _rows(div, bill_no, party_code):
    """All rows for one bill (the table has no key: DIV + bill no + party identifies it)."""
    return Bill.objects.filter(div=div, bill_no=bill_no, party_code=party_code)


def _money(value):
    return f"{(value or 0):.2f}"


def party_names(codes):
    return dict(Party.objects.filter(party_code__in=set(codes)).values_list("party_code", "name"))


def list_bills(div=DEFAULT_DIV):
    """Bills of one division ('' = all), sorted by date then invoice no."""
    qs = Bill.objects.all()
    if div:
        qs = qs.filter(div=div)
    rows = list(qs.order_by("bill_date", "bill_no").values(
        "div", "bill_no", "bill_date", "party_code", "net_amount", "cash_discount"
    ))
    names = party_names(r["party_code"] for r in rows)
    result = []
    for sno, r in enumerate(rows, start=1):
        div_, bill_no, party = (r["div"] or "").strip(), (r["bill_no"] or "").strip(), (r["party_code"] or "").strip()
        result.append({
            "sno": sno,
            "key": f"{div_}|{bill_no}|{party}",
            "div": div_,
            "bill_no": bill_no,
            "bill_date": r["bill_date"].isoformat() if r["bill_date"] else "",
            "party_code": party,
            "party_name": (names.get(r["party_code"]) or "").strip(),
            "net_amount": _money(r["net_amount"]),
            "cash_discount": _money(r["cash_discount"]),
        })
    return result


def divisions():
    return sorted({(d or "").strip() for d in Bill.objects.values_list("div", flat=True).distinct() if d})


def search_parties(term, limit=15):
    """Party Master lookup by code or name (for the PARTY field).
    A blank term returns the first parties (by name) so the Party Help popup
    has something to show as soon as it opens, instead of "No matches"."""
    term = (term or "").strip()
    if not term:
        qs = Party.objects.order_by("name")
    else:
        qs = Party.objects.filter(party_code__istartswith=term) | Party.objects.filter(name__icontains=term)
        qs = qs.order_by("name")
    return [
        {"code": c, "name": (n or "").strip(), "city": (city or "").strip()}
        for c, n, city in qs.values_list("party_code", "name", "city")[:limit]
    ]


def has_receipts(div, bill_no, party_code):
    """True when money is already recorded against this bill (receipts / collections)."""
    bill = _rows(div, bill_no, party_code).values("amount_received", "payment_received").first()
    if bill and ((bill["amount_received"] or 0) != 0 or (bill["payment_received"] or "").strip().upper() == "Y"):
        return True
    connection = connections[_db()]
    if connection.vendor != "microsoft":
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT TOP 1 1 FROM [p_col] WHERE [bill_no] = %s AND [p_code] = %s", [bill_no, party_code])
        return cursor.fetchone() is not None


def _check_single(div, bill_no, party_code):
    count = _rows(div, bill_no, party_code).count()
    if count == 0:
        raise OutstandingError("This entry no longer exists — refresh the list.")
    if count > 1:
        raise OutstandingError(
            f"There are {count} identical entries for {div}/{bill_no} ({party_code}); "
            "it cannot be changed here to avoid touching the wrong one."
        )


def create(data, username=""):
    """ADD: insert one bill row, like the old BILLPY rpldata."""
    if _rows(data["div"], data["bill_no"], data["party_code"]).exists():
        raise OutstandingError(
            f"Invoice {data['div']}/{data['bill_no']} already exists for this party."
        )
    with transaction.atomic(using=_db()):
        Bill(
            div=data["div"], bill_no=data["bill_no"], bill_date=data["bill_date"],
            party_code=data["party_code"], net_amount=data["net_amount"], amount=data["net_amount"],
            cash_discount=data["cash_discount"],
        ).save(force_insert=True)
        fill_blank_columns(_db(), "bill", "bill_no", data["bill_no"], username,
                           extra_keys={"div": data["div"], "p_code": data["party_code"]})


def update(key, data):
    """MODIFY: change the selected bill row (identified by its old DIV / bill no / party)."""
    div, bill_no, party_code = key
    _check_single(div, bill_no, party_code)
    if has_receipts(div, bill_no, party_code):
        raise OutstandingError("A receipt is already recorded against this bill; it cannot be modified.")
    new_key = (data["div"], data["bill_no"], data["party_code"])
    if new_key != tuple(key) and _rows(*new_key).exists():
        raise OutstandingError(f"Invoice {data['div']}/{data['bill_no']} already exists for this party.")
    with transaction.atomic(using=_db()):
        _rows(div, bill_no, party_code).update(
            div=data["div"], bill_no=data["bill_no"], bill_date=data["bill_date"],
            party_code=data["party_code"], net_amount=data["net_amount"], amount=data["net_amount"],
            cash_discount=data["cash_discount"],
        )


def delete(key):
    """DELETE: remove the selected bill row, unless money is already recorded against it."""
    div, bill_no, party_code = key
    _check_single(div, bill_no, party_code)
    if has_receipts(div, bill_no, party_code):
        raise OutstandingError("A receipt is already recorded against this bill; it cannot be deleted.")
    with transaction.atomic(using=_db()):
        _rows(div, bill_no, party_code).delete()

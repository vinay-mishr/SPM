"""
Opening Balance Master — party opening balances (old software: cust_mst.cyob).

One signed number per party: positive = Debit, negative = Credit, so a party can
never have both. The grid shows it split into Debit / Credit columns; saving joins
them back (cyob = debit - credit). Only cyob is written — nothing else changes.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, Value, When

from .models import Party

ZERO = Decimal("0.00")
MAX_AMOUNT = Decimal("99999999999.99")  # cyob is decimal(13, 2)
PERMISSION = "parties.change_opening_balance"


class OpeningBalanceError(Exception):
    """Validation problem; ``errors`` maps party code -> message."""

    def __init__(self, errors):
        super().__init__("Some opening balances are not valid.")
        self.errors = errors


def split(balance):
    """Signed balance -> (debit, credit)."""
    balance = balance or ZERO
    return (balance, ZERO) if balance >= 0 else (ZERO, -balance)


def _money(value):
    return f"{value:.2f}"


def rows():
    """All parties sorted by name (as the old grid), with debit / credit split out."""
    result = []
    parties = Party.objects.order_by("name").values_list("party_code", "name", "gst_no", "opening_balance")
    for sno, (code, name, gst_no, balance) in enumerate(parties, start=1):
        debit, credit = split(balance)
        result.append({
            "sno": sno,
            "code": (code or "").strip() or code,
            "id": code,
            "name": (name or "").strip(),
            "gst_no": "" if (gst_no or "").strip() == "." else (gst_no or "").strip(),
            "debit": _money(debit),
            "credit": _money(credit),
        })
    return result


def totals():
    """Debit and credit totals over ALL parties (not only the rows shown)."""
    zero = Value(ZERO, output_field=DecimalField(max_digits=15, decimal_places=2))
    sums = Party.objects.aggregate(
        debit=Sum(Case(When(opening_balance__gt=0, then=F("opening_balance")), default=zero)),
        credit=Sum(Case(When(opening_balance__lt=0, then=-F("opening_balance")), default=zero)),
    )
    return {"debit": _money(sums["debit"] or ZERO), "credit": _money(sums["credit"] or ZERO)}


def parse_amount(raw):
    """'1000.50' -> Decimal('1000.50'); blank -> 0. Raises ValueError with a message."""
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if text == "":
        return ZERO
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("Enter a number (for example 1000.50).")
    if not value.is_finite():
        raise ValueError("Enter a number (for example 1000.50).")
    if value < 0:
        raise ValueError("Amounts cannot be negative — use the Credit column for credit balances.")
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("Use at most 2 decimal places.")
    if value > MAX_AMOUNT:
        raise ValueError("Amount is too large (maximum 99,999,999,999.99).")
    return value.quantize(Decimal("0.01"))


def save(changes):
    """
    Save changed rows: [{"code": ..., "debit": ..., "credit": ...}, ...].
    Every row is validated first; then all are written in one transaction (all or nothing).
    Returns the number of parties updated.
    """
    if not isinstance(changes, list) or not changes:
        raise OpeningBalanceError({"": "No changes to save."})

    errors, balances = {}, {}
    for change in changes:
        code = str((change or {}).get("code", ""))
        try:
            debit = parse_amount(change.get("debit"))
            credit = parse_amount(change.get("credit"))
        except ValueError as exc:
            errors[code] = str(exc)
            continue
        if debit and credit:
            errors[code] = "A party can have a Debit or a Credit opening balance, not both."
            continue
        balances[code] = debit - credit

    existing = set(Party.objects.filter(party_code__in=list(balances)).values_list("party_code", flat=True))
    for code in balances:
        if code not in existing:
            errors[code] = "Party not found."
    if errors:
        raise OpeningBalanceError(errors)

    with transaction.atomic(using=Party.objects.db):
        for code, balance in balances.items():
            Party.objects.filter(party_code=code).update(opening_balance=balance)
    return len(balances)

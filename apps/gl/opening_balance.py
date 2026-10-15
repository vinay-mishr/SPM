"""
Main Ledger (Op. Balance) — general ledger opening balances (old software:
gled_mst.gyob; old VFP form opened gled_mst ORDER gdesc, plus a read-only look at
cust_mst.cyob that the old form never actually wrote back -- see ``rows()``).

One signed number per ledger: positive = Debit, negative = Credit, so a ledger can
never have both. The grid shows it split into Debit / Credit columns; saving joins
them back (gyob = debit - credit). Only gyob is written -- nothing else changes.
Same convention as Party Master's Opening Balance Master (apps/parties/opening_balance.py).
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, Value, When

from .models import Ledger

ZERO = Decimal("0.00")
MAX_AMOUNT = Decimal("9999999999999.99")  # gyob is decimal(13, 2), but never negative here
PERMISSION = "gl.change_ledger_opening_balance"


class OpeningBalanceError(Exception):
    """Validation problem; ``errors`` maps ledger code -> message."""

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
    """All ledgers ordered by description (as the old grid), with debit / credit split out."""
    result = []
    ledgers = Ledger.objects.order_by("description").values_list("ledger_code", "description", "opening_balance")
    for sno, (code, description, balance) in enumerate(ledgers, start=1):
        debit, credit = split(balance)
        result.append({
            "sno": sno,
            "code": (code or "").strip() or code,
            "id": code,
            "description": (description or "").strip(),
            "debit": _money(debit),
            "credit": _money(credit),
        })
    return result


def totals():
    """Debit and Credit totals over ALL ledgers, plus the old screen's Difference /
    G.Total rows: whichever side is smaller is topped up to match the larger side,
    so Debit and Credit always foot to the same grand total."""
    zero = Value(ZERO, output_field=DecimalField(max_digits=15, decimal_places=2))
    sums = Ledger.objects.aggregate(
        debit=Sum(Case(When(opening_balance__gt=0, then=F("opening_balance")), default=zero)),
        credit=Sum(Case(When(opening_balance__lt=0, then=-F("opening_balance")), default=zero)),
    )
    debit_total = sums["debit"] or ZERO
    credit_total = sums["credit"] or ZERO
    diff_debit = credit_total - debit_total if credit_total >= debit_total else ZERO
    diff_credit = debit_total - credit_total if debit_total >= credit_total else ZERO
    return {
        "debit": _money(debit_total),
        "credit": _money(credit_total),
        "diff_debit": _money(diff_debit),
        "diff_credit": _money(diff_credit),
        "grand_debit": _money(debit_total + diff_debit),
        "grand_credit": _money(credit_total + diff_credit),
    }


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
        raise ValueError("Amount is too large.")
    return value.quantize(Decimal("0.01"))


def save(changes):
    """
    Save changed rows: [{"code": ..., "debit": ..., "credit": ...}, ...].
    Every row is validated first; then all are written in one transaction (all or nothing).
    Returns the number of ledgers updated.
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
            errors[code] = "A ledger can have a Debit or a Credit opening balance, not both."
            continue
        balances[code] = debit - credit

    existing = set(Ledger.objects.filter(ledger_code__in=list(balances)).values_list("ledger_code", flat=True))
    for code in balances:
        if code not in existing:
            errors[code] = "Ledger not found."
    if errors:
        raise OpeningBalanceError(errors)

    with transaction.atomic(using=Ledger.objects.db):
        for code, balance in balances.items():
            Ledger.objects.filter(ledger_code=code).update(opening_balance=balance)
    return len(balances)

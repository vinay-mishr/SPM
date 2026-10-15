"""
Quotation arithmetic -- the single source of truth for every amount saved. The entry
screen's JavaScript (quotation_entry.js, ``calcLine`` / ``calcTotals``) mirrors these
rules for instant feedback, but the server always recomputes and never trusts the
browser's totals.

Pricing is tax-exclusive, as in the legacy "caltotal" routine:
    gross     = qty x rate
    discount  = round(gross x disc% / 100, 2)     (or an entered amount, % derived)
    taxable   = gross - discount
    GST       = round(taxable x GST% / 100, 2)     only when GST (Y/N) is 'Y'
    net       = sum(gross) - sum(discount) + sum(GST)
All rounding is ROUND_HALF_UP to 2 decimals.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


class CalcError(ValueError):
    pass


def to_decimal(value, label="value"):
    if value is None or (isinstance(value, str) and not value.strip()):
        return ZERO
    try:
        result = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        raise CalcError(f"{label} must be a number.")
    if not result.is_finite():
        raise CalcError(f"{label} must be a number.")
    return result


def q2(value):
    return Decimal(value).quantize(Q2, ROUND_HALF_UP)


def calc_line(qty, rate, disc_pct=ZERO, disc_amt=ZERO, gst_pct=ZERO, gst_applicable=True):
    """
    Amounts for one line. A discount % wins when it is above zero; otherwise an
    entered discount amount is used and the % is derived from it.
    """
    qty, rate = Decimal(qty), Decimal(rate)
    disc_pct, disc_amt, gst_pct = Decimal(disc_pct), Decimal(disc_amt), Decimal(gst_pct)
    gross = q2(qty * rate)
    if disc_pct > 0:
        discount = q2(gross * disc_pct / HUNDRED)
    elif disc_amt > 0:
        discount = q2(disc_amt)
        disc_pct = q2(discount * HUNDRED / gross) if gross else ZERO
    else:
        discount, disc_pct = ZERO, ZERO
    taxable = gross - discount
    gst = q2(taxable * gst_pct / HUNDRED) if gst_applicable else ZERO
    return {
        "gross": gross,
        "disc_pct": q2(disc_pct),
        "discount": q2(discount),
        "taxable": q2(taxable),
        "gst_pct": q2(gst_pct),
        "gst": gst,
        "total": q2(taxable + gst),
    }


def calc_totals(lines):
    total = sum((l["gross"] for l in lines), ZERO)
    discount = sum((l["discount"] for l in lines), ZERO)
    gst = sum((l["gst"] for l in lines), ZERO)
    return {"total": q2(total), "discount": q2(discount), "gst": q2(gst), "net": q2(total - discount + gst)}

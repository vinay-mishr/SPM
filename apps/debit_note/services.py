"""GST Purchase Debit Note: numbering, GST split, locks, list and detail."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction

from apps.parties.models import Party

from .models import DebitNote, DebitNoteCounter

RATES = ["0", "5", "12", "18", "28"]
Q2 = Decimal("0.01")


class DebitNoteError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _d(value):
    try:
        return Decimal(str(value or "0").strip() or "0")
    except InvalidOperation:
        return None


def _date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _highest_number():
    numbers = [int(n) for n in DebitNote.objects.values_list("dn_no", flat=True) if (n or "").isdigit()]
    return max(numbers, default=0)


def next_no():
    counter = DebitNoteCounter.objects.first()
    return str(max(counter.last_no if counter else 0, _highest_number()) + 1)


def _issue_no():
    counter = DebitNoteCounter.objects.select_for_update().first()
    if counter is None:
        counter = DebitNoteCounter.objects.create(last_no=0)
    counter.last_no = max(counter.last_no, _highest_number()) + 1
    counter.save(update_fields=["last_no"])
    return str(counter.last_no)


def compute(taxable, interstate, cess):
    """Per purchase rate: interstate gives IGST, within state gives CGST + SGST (half each)."""
    gst = {}
    base = Decimal("0")
    tax_total = Decimal("0")
    for rate in RATES:
        t = taxable.get(rate, Decimal("0"))
        tax = (t * Decimal(rate) / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
        if interstate:
            gst[rate] = {"cgst": "0.00", "sgst": "0.00", "igst": f"{tax:.2f}"}
        else:
            half = (tax / 2).quantize(Q2, ROUND_HALF_UP)
            gst[rate] = {"cgst": f"{half:.2f}", "sgst": f"{tax - half:.2f}", "igst": "0.00"}
        base += t
        tax_total += tax
    total = (base + tax_total + cess).quantize(Q2, ROUND_HALF_UP)
    return gst, total


def _validate(payload):
    errors = {}
    dn_no = (payload.get("dn_no") or "").strip()
    if not dn_no.isdigit():
        errors["dn_no"] = "D.N. no. must be a number."
    dn_date = _date(payload.get("dn_date"))
    if not dn_date:
        errors["dn_date"] = "Enter the D.N. date."
    code = (payload.get("party_code") or "").strip().upper()
    party = Party.objects.filter(party_code=code).first() if code else None
    if not party:
        errors["party_code"] = "Select a party."
    taxable = {}
    for rate in RATES:
        v = _d((payload.get("taxable") or {}).get(rate))
        if v is None or v < 0:
            errors["taxable_" + rate] = f"PUR {rate}% taxable value is invalid."
        else:
            taxable[rate] = v
    cess = _d(payload.get("cess")) or Decimal("0")
    if cess < 0:
        errors["cess"] = "Cess can't be negative."
    if errors:
        raise DebitNoteError("Fix the highlighted fields.", errors)
    return dn_no, dn_date, party, taxable, cess


def save(payload, key=None, username=""):
    dn_no, dn_date, party, taxable, cess = _validate(payload)
    interstate = bool(payload.get("interstate"))
    gst, total = compute(taxable, interstate, cess)
    narration = "\n".join((payload.get("narration") or "").split("\n")[:4])[:1000]
    with transaction.atomic():
        if key:
            note = DebitNote.objects.select_for_update().filter(dn_no=key).first()
            if not note:
                raise DebitNoteError("This debit note no longer exists.")
            if note.locked:
                raise DebitNoteError("Unable to Modify: this debit note is locked.")
            if DebitNote.objects.exclude(pk=note.pk).filter(dn_no=dn_no).exists():
                raise DebitNoteError("D.N. no. already exists.", {"dn_no": "D.N. no. already exists."})
        else:
            if DebitNote.objects.filter(dn_no=dn_no).exists():
                raise DebitNoteError("D.N. no. already exists.", {"dn_no": "D.N. no. already exists."})
            note = DebitNote(kind="N")
        note.dn_no = dn_no
        note.dn_date = dn_date
        note.invoice_no = (payload.get("invoice_no") or "").strip()[:20]
        note.invoice_date = _date(payload.get("invoice_date"))
        note.party_code = party.party_code
        note.party_name = (party.name or "").strip()[:60]
        note.party_city = (party.city or "").strip()[:40]
        note.place_of_supply = (payload.get("place_of_supply") or "").strip()[:40]
        note.narration = narration
        note.taxable = {k: f"{v:.2f}" for k, v in taxable.items()}
        note.gst = gst
        note.cess = cess
        note.total_amount = total
        note.net_rounded = total.quantize(Decimal("1"), ROUND_HALF_UP)
        note.uname = username[:150]
        note.save()
    return {"dn_no": dn_no, "total": f"{total:.2f}"}


def new_note_save(payload, username=""):
    with transaction.atomic():
        number = _issue_no()
        body = dict(payload, dn_no=number)
        return save(body, key=None, username=username)


def delete(dn_no):
    with transaction.atomic():
        note = DebitNote.objects.select_for_update().filter(dn_no=dn_no).first()
        if not note:
            raise DebitNoteError("Debit note not found.")
        if note.locked:
            raise DebitNoteError("Unable to Delete: this debit note is locked.")
        note.delete()
    return {"dn_no": dn_no}


def list_notes(start, end, search=""):
    term = (search or "").strip().lower()
    rows = []
    for n in DebitNote.objects.filter(dn_date__gte=start, dn_date__lte=end):
        if term and term not in n.party_name.lower():
            continue
        rows.append({"key": n.dn_no, "dn_no": n.dn_no, "date": n.dn_date.isoformat(),
                     "bill_no": n.invoice_no, "bill_date": n.invoice_date.isoformat() if n.invoice_date else "",
                     "party_code": n.party_code, "net": f"{n.net_rounded:.2f}",
                     "party": n.party_name, "city": n.party_city})
    rows.sort(key=lambda r: (r["date"], int(r["dn_no"]) if r["dn_no"].isdigit() else 0), reverse=True)
    return rows


def detail(dn_no):
    n = DebitNote.objects.filter(dn_no=dn_no).first()
    if not n:
        return None
    return {"dn_no": n.dn_no, "dn_date": n.dn_date.isoformat(), "invoice_no": n.invoice_no,
            "invoice_date": n.invoice_date.isoformat() if n.invoice_date else "",
            "party_code": n.party_code, "party_name": n.party_name, "place_of_supply": n.place_of_supply,
            "narration": n.narration, "taxable": n.taxable, "gst": n.gst, "cess": f"{n.cess:.2f}",
            "total": f"{n.total_amount:.2f}", "net_rounded": f"{n.net_rounded:.2f}", "locked": n.locked,
            "interstate": any(v.get("igst", "0.00") != "0.00" for v in (n.gst or {}).values())}

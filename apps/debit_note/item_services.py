"""Debit Note Entry (item-based): items, discount, GST and totals as on the VFP DEBIT NOTE form."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.db.models import F

from apps.bom.services import search_parts  # noqa: F401
from apps.parts.models import Part
from apps.parties.models import Party
from apps.purchase_orders.models import ItemMasterTransaction
from apps.creditor_outstanding.models import CreditorBill

from .item_models import DebitNoteItemLine
from .legacy_models import DebitNoteBill
from .models import DebitNote
from .services import DebitNoteError, _issue_no, next_no  # noqa: F401

DIV = "OL"
GST_RATES = (0, 5, 12, 18, 28)

Q2 = Decimal("0.01")


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


def totals(lines, freight, freight_gst_pct):
    gross = Decimal("0")
    dis = Decimal("0")
    gst = Decimal("0")
    qty = Decimal("0")
    for ln in lines:
        base = ln["qty"] * ln["rate"]
        d = (base * ln["dis_pct"] / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
        amount = (base - d).quantize(Q2, ROUND_HALF_UP)
        gross += amount
        dis += d
        gst += (amount * ln["gst_pct"] / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
        qty += ln["qty"]
        ln["amount"] = amount
        ln["dis_amt"] = d
    freight_gst = (freight * freight_gst_pct / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
    net = (gross + gst + freight + freight_gst).quantize(Q2, ROUND_HALF_UP)
    return {"qty": qty, "amount": gross, "dis": dis, "gst": gst, "freight_gst": freight_gst, "net": net}


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
    raw = payload.get("items") or []
    if not raw:
        errors["items"] = "Add at least one item."
    lines = []
    for n, r in enumerate(raw, start=1):
        item = Part.objects.filter(part_number=(r.get("item_code") or "").strip().upper()).first()
        if not item:
            errors["items"] = f"Row {n}: item isn't in the Item Master."
            break
        qty = _d(r.get("qty"))
        rate = _d(r.get("rate"))
        dis = _d(r.get("dis_pct")) or Decimal("0")
        if qty is None or qty <= 0:
            errors["items"] = f"Row {n}: quantity must be greater than zero."
            break
        if rate is None or rate < 0:
            errors["items"] = f"Row {n}: rate can't be negative."
            break
        gst_pct = Decimal(str(item.gst_percent or 0))
        if int(gst_pct) not in GST_RATES or gst_pct != int(gst_pct):
            errors["items"] = f"Row {n}: {item.part_number}'s GST % ({gst_pct}) must be one of 0, 5, 12, 18 or 28."
            break
        lines.append({"item_code": item.part_number, "item_name": (item.description_1 or "")[:60],
                      "hsn_code": (item.hsn_code or "")[:8], "unit": (item.unit or "")[:3],
                      "qty": qty, "rate": rate, "mrp": _d(r.get("mrp")) or Decimal("0"),
                      "dis_pct": dis, "gst_pct": gst_pct})
    freight = _d(payload.get("freight")) or Decimal("0")
    freight_gst_pct = _d(payload.get("freight_gst_pct")) or Decimal("0")
    if errors:
        raise DebitNoteError("Fix the highlighted fields.", errors)
    return dn_no, dn_date, party, lines, freight, freight_gst_pct


def _legacy_enabled():
    return "legacy" in settings.DATABASES and settings.LEGACY_WRITES_ENABLED


def _reverse_legacy(dn_no, party_code):
    """Undo a previous _post_legacy() for this debit note: restores part-mst stock,
    removes its imaster lines, reverses the cr_out bill's dr_amt, and removes its
    d_bill row. Mirrors the VFP deldata routine (ledger/trans reversal excluded --
    see legacy_models.py)."""
    if not _legacy_enabled() or not dn_no or not party_code:
        return
    with transaction.atomic(using="legacy"):
        old_lines = list(ItemMasterTransaction.objects.filter(
            debit_note_no=dn_no, party_code=party_code, status="A").values("item_code", "quantity"))
        for ol in old_lines:
            if ol["item_code"]:
                Part.objects.filter(part_number=ol["item_code"]).update(
                    current_stock=F("current_stock") + (ol["quantity"] or Decimal("0")))
        ItemMasterTransaction.objects.filter(
            debit_note_no=dn_no, party_code=party_code, status="A").delete()

        bills = list(DebitNoteBill.objects.filter(grn_no=dn_no, party_code=party_code)
                     .values("bill_no", "bill_date", "net_amount")[:1])
        if bills:
            b = bills[0]
            if b["bill_no"] and b["bill_date"]:
                CreditorBill.objects.filter(
                    p_code=party_code, inv_no=b["bill_no"], inv_dt=b["bill_date"]).update(
                    dr_amt=F("dr_amt") - (b["net_amount"] or Decimal("0")), pmt_mad="N")
            DebitNoteBill.objects.filter(grn_no=dn_no, party_code=party_code).delete()


def _post_legacy(note, lines, party, freight, freight_gst_pct, t, username):
    """Post this debit note into the legacy SQL Server tables the same way the VFP
    GST DEBIT NOTE form's rpldata routine does: one imaster line per item (status 'A'),
    part-mst stock reduced by each line's quantity, a d_bill header with the GST
    bucketed totals, and the matching cr_out bill's dr_amt increased. Ledger (trans)
    postings are intentionally NOT made -- see legacy_models.py for why."""
    if not _legacy_enabled():
        return
    intra_state = (party.supply_type or "").strip().upper() != "I"
    buckets = {r: [Decimal("0"), Decimal("0")] for r in (5, 12, 18, 28)}
    taxable_0 = Decimal("0")
    imaster_rows = []

    with transaction.atomic(using="legacy"):
        for ln in lines:
            rate = int(ln["gst_pct"])
            gst_amt = (ln["amount"] * ln["gst_pct"] / Decimal("100")).quantize(Q2, ROUND_HALF_UP)
            if rate == 0:
                taxable_0 += ln["amount"]
                cgst_rt = sgst_rt = igst_rt = Decimal("0")
                cgst_amt = sgst_amt = igst_amt = Decimal("0")
            else:
                buckets[rate][0] += ln["amount"]
                buckets[rate][1] += gst_amt
                if intra_state:
                    cgst_rt = sgst_rt = ln["gst_pct"] / 2
                    cgst_amt = sgst_amt = (gst_amt / 2).quantize(Q2, ROUND_HALF_UP)
                    igst_rt = igst_amt = Decimal("0")
                else:
                    igst_rt, igst_amt = ln["gst_pct"], gst_amt
                    cgst_rt = sgst_rt = cgst_amt = sgst_amt = Decimal("0")
            imaster_rows.append(ItemMasterTransaction(
                div=DIV, item_code=ln["item_code"], party_code=party.party_code,
                bill_no=note.invoice_no, bill_date=note.invoice_date or note.dn_date,
                debit_note_no=note.dn_no, debit_note_date=note.dn_date, hsn_code=ln["hsn_code"],
                quantity=ln["qty"], rate=ln["rate"], amount=ln["amount"],
                discount_percent=ln["dis_pct"], discount_amount=ln["dis_amt"],
                gst_percent=ln["gst_pct"], gst_amount=gst_amt,
                cgst_rate=cgst_rt, cgst_amount=cgst_amt, sgst_rate=sgst_rt, sgst_amount=sgst_amt,
                igst_rate=igst_rt, igst_amount=igst_amt, status="A", uname=(username or "")[:10],
            ))
            Part.objects.filter(part_number=ln["item_code"]).update(
                current_stock=F("current_stock") - ln["qty"])
        ItemMasterTransaction.objects.bulk_create(imaster_rows)

        bill = DebitNoteBill(
            div=DIV, bill_no=note.invoice_no, bill_date=note.invoice_date, party_code=party.party_code,
            amount=t["amount"], net_amount=t["net"], gr_no=note.gr_no, gr_date=note.gr_date,
            transport=note.transport, grn_no=note.dn_no, grn_date=note.dn_date,
            ag_pur=note.invoice_no, ag_date=note.invoice_date, date=note.dn_date,
            dis_amt=t["dis"], gst_amt=t["gst"] + t["freight_gst"], cstat=party.supply_type, pur_type="S",
            freight_rate=freight_gst_pct, freight_amount=freight, freight_gst_amount=t["freight_gst"],
            taxable_0=taxable_0, taxable_0_alt=taxable_0, purch_0=taxable_0,
            uname=(username or "")[:10],
        )
        for rate, (base, gst_amt_total) in buckets.items():
            setattr(bill, f"taxable_{rate}", base)
            setattr(bill, f"purch_{rate}", base)
            if intra_state:
                half = (gst_amt_total / 2).quantize(Q2, ROUND_HALF_UP)
                for prefix in ("cgst_rt", "cgst_amt", "cgst_am"):
                    setattr(bill, f"{prefix}{rate}", half if "amt" in prefix else Decimal(rate) / 2)
                for prefix in ("sgst_rt", "sgst_amt", "sgst_am"):
                    setattr(bill, f"{prefix}{rate}", half if "amt" in prefix else Decimal(rate) / 2)
            else:
                for prefix in ("igst_rt",):
                    setattr(bill, f"{prefix}{rate}", Decimal(rate))
                for prefix in ("igst_amt", "igst_am"):
                    setattr(bill, f"{prefix}{rate}", gst_amt_total)
        DebitNoteBill.objects.bulk_create([bill])

        if note.invoice_no and note.invoice_date:
            cr_rows = list(CreditorBill.objects.filter(
                p_code=party.party_code, inv_no=note.invoice_no, inv_dt=note.invoice_date
            ).values("amount", "pmt_rcd", "dr_amt")[:1])
            if cr_rows:
                cr = cr_rows[0]
                new_dr = (cr["dr_amt"] or Decimal("0")) + t["net"]
                paid_off = (cr["amount"] or Decimal("0")) <= (cr["pmt_rcd"] or Decimal("0")) + new_dr
                CreditorBill.objects.filter(
                    p_code=party.party_code, inv_no=note.invoice_no, inv_dt=note.invoice_date
                ).update(dr_amt=new_dr, nar=note.invoice_no, uname=(username or "")[:10],
                         pmt_mad="Y" if paid_off else "N")


def save_items(payload, key=None, username=""):
    dn_no, dn_date, party, lines, freight, freight_gst_pct = _validate(payload)
    t = totals(lines, freight, freight_gst_pct)
    old_dn_no = old_party_code = None
    with transaction.atomic():
        if key:
            note = DebitNote.objects.select_for_update().filter(dn_no=key).first()
            if not note:
                raise DebitNoteError("This debit note no longer exists.")
            if note.locked:
                raise DebitNoteError("Unable to Modify: this debit note is locked.")
            if DebitNote.objects.exclude(pk=note.pk).filter(dn_no=dn_no).exists():
                raise DebitNoteError("D.N. no. already exists.", {"dn_no": "D.N. no. already exists."})
            old_dn_no, old_party_code = note.dn_no, note.party_code
            note.item_lines.all().delete()
        else:
            note = DebitNote(kind="E")
        note.dn_no = dn_no
        note.dn_date = dn_date
        note.invoice_no = (payload.get("invoice_no") or "").strip()[:20]
        note.invoice_date = _date(payload.get("invoice_date"))
        note.gr_no = (payload.get("gr_no") or "").strip()[:20]
        note.gr_date = _date(payload.get("gr_date"))
        note.transport = (payload.get("transport") or "").strip()[:40]
        note.party_code = party.party_code
        note.party_name = (party.name or "").strip()[:60]
        note.party_city = (party.city or "").strip()[:40]
        note.place_of_supply = (payload.get("place_of_supply") or "").strip()[:40]
        note.freight = freight
        note.freight_gst_pct = freight_gst_pct
        note.total_amount = t["net"]
        note.net_rounded = t["net"].quantize(Decimal("1"), ROUND_HALF_UP)
        note.uname = username[:150]
        note.save()
        DebitNoteItemLine.objects.bulk_create([
            DebitNoteItemLine(note=note, line_no=n,
                              **{k: v for k, v in ln.items() if k not in ("amount", "dis_amt")})
            for n, ln in enumerate(lines, start=1)
        ])

    # Legacy SQL Server mirror (imaster / part-mst / d_bill / cr_out). Ledger (trans)
    # postings are intentionally not made -- see legacy_models.py and _post_legacy().
    if old_dn_no:
        _reverse_legacy(old_dn_no, old_party_code)
    _post_legacy(note, lines, party, freight, freight_gst_pct, t, username)
    return {"dn_no": dn_no, "net": f"{t['net']:.2f}"}


def new_save_items(payload, username=""):
    with transaction.atomic():
        number = _issue_no()
        return save_items(dict(payload, dn_no=number), key=None, username=username)


def delete_items(dn_no):
    note = DebitNote.objects.filter(dn_no=dn_no, kind="E").first()
    if not note:
        raise DebitNoteError("Debit note not found.")
    if note.locked:
        raise DebitNoteError("Unable to Delete: this debit note is locked.")
    deleted_dn_no, party_code = note.dn_no, note.party_code
    with transaction.atomic():
        note.delete()
    _reverse_legacy(deleted_dn_no, party_code)
    return {"dn_no": dn_no}


def detail_items(dn_no):
    note = DebitNote.objects.filter(dn_no=dn_no, kind="E").first()
    if not note:
        return None
    lines = [{"item_code": l.item_code, "item_name": l.item_name, "hsn_code": l.hsn_code, "unit": l.unit,
              "qty": f"{l.qty:.3f}", "rate": f"{l.rate:.2f}", "mrp": f"{l.mrp:.2f}",
              "dis_pct": f"{l.dis_pct:.2f}", "gst_pct": f"{l.gst_pct:.2f}"} for l in note.item_lines.all()]
    return {"dn_no": note.dn_no, "dn_date": note.dn_date.isoformat(), "invoice_no": note.invoice_no,
            "invoice_date": note.invoice_date.isoformat() if note.invoice_date else "",
            "gr_no": note.gr_no, "gr_date": note.gr_date.isoformat() if note.gr_date else "",
            "transport": note.transport, "party_code": note.party_code, "party_name": note.party_name,
            "place_of_supply": note.place_of_supply, "freight": f"{note.freight:.2f}",
            "freight_gst_pct": f"{note.freight_gst_pct:.2f}", "net": f"{note.total_amount:.2f}",
            "locked": note.locked, "items": lines}


def list_items(start, end, search=""):
    term = (search or "").strip().lower()
    rows = []
    for n in DebitNote.objects.filter(kind="E", dn_date__gte=start, dn_date__lte=end):
        if term and term not in n.party_name.lower():
            continue
        rows.append({"key": n.dn_no, "dn_no": n.dn_no, "date": n.dn_date.isoformat(),
                     "bill_no": n.invoice_no, "bill_date": n.invoice_date.isoformat() if n.invoice_date else "",
                     "party_code": n.party_code, "party": n.party_name, "city": n.party_city,
                     "net": f"{n.total_amount:.2f}"})
    rows.sort(key=lambda r: (r["date"], int(r["dn_no"]) if r["dn_no"].isdigit() else 0))
    return rows

"""
E-Way Bill module services -- built entirely on top of apps.gst_invoice's own
existing data (the legacy ``bill``/``i_master``/``cust_mst`` tables, read via
apps.gst_invoice.services). No invoice data is duplicated here; this module
only tracks the e-way-bill-specific workflow (apps.eway_bill.models.EwayBill)
and talks to the provider (apps.eway_bill.provider).
"""
from datetime import datetime, date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.gst_invoice import services as gi_services

from . import provider
from .models import EwayBill
from .provider import ProviderError

MANDATORY_TRANSPORT_FIELDS = ("transport_mode", "distance_km")


class EwayBillError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _d(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def list_eligible(start, end, search=""):
    """GST invoices in range, each tagged with its e-way-bill status (if any
    generation has been attempted) -- reuses gst_invoice.services.list_invoices
    verbatim rather than re-querying the legacy ``bill`` table."""
    rows = gi_services.list_invoices(start, end, search)
    bill_nos = [r["bill_no"] for r in rows]
    statuses = {e.bill_no: e for e in EwayBill.objects.filter(bill_no__in=bill_nos)}
    for r in rows:
        e = statuses.get(r["bill_no"])
        r["eway_status"] = e.get_status_display() if e else "Not Generated"
        r["eway_bill_no"] = e.eway_bill_no if e else ""
        r["ack_no"] = e.ack_no if e else ""
    return rows


def _eway_row(bill_no):
    return EwayBill.objects.filter(bill_no=bill_no).first()


def effective_transport(invoice, e):
    """Fields that genuinely exist elsewhere in the database and are pulled in
    automatically -- recipient PIN and the party's own default transporter
    come from cust_mst (pin/ctrp, read via gst_invoice.services.get_invoice()'s
    party_pin/party_transport), vehicle no from the invoice's own vehi_no.
    A manually-entered EwayBill value always wins if one was saved. Only
    transporter GSTIN, transport mode, distance and the transport document
    number have no source anywhere in this schema, so they stay manual."""
    return {
        "recipient_pincode": (e.recipient_pincode if e else "") or invoice.get("party_pin") or "",
        "transporter_name": (e.transporter_name if e else "")
            or invoice.get("party_transport") or invoice.get("transport") or "",
        "vehicle_no": (e.vehicle_no if e else "") or invoice.get("vehicle_no") or "",
        "transporter_gstin": e.transporter_gstin if e else "",
        "transport_mode": e.transport_mode if e else "",
        "transport_doc_no": e.transport_doc_no if e else "",
        "transport_doc_date": e.transport_doc_date if e else None,
        "distance_km": e.distance_km if e else None,
    }


def get_detail(bill_no):
    """Full detail for the right-hand response/status panel: the GST invoice
    data (reused as-is from apps.gst_invoice) plus whatever e-way-bill
    generation state/response already exists for it."""
    invoice = gi_services.get_invoice(bill_no)
    if not invoice:
        return None
    e = _eway_row(bill_no)
    return {
        "invoice": invoice,
        "eway": _serialize(e or EwayBill(bill_no=bill_no), invoice),
        "validation": validate(invoice, e),
    }


def _serialize(e, invoice=None):
    eff = effective_transport(invoice, e) if invoice is not None else {
        "recipient_pincode": e.recipient_pincode, "transporter_name": e.transporter_name,
        "vehicle_no": e.vehicle_no, "transporter_gstin": e.transporter_gstin,
        "transport_mode": e.transport_mode, "transport_doc_no": e.transport_doc_no,
        "transport_doc_date": e.transport_doc_date, "distance_km": e.distance_km,
    }
    return {
        "bill_no": e.bill_no,
        "status": e.status,
        "status_label": e.get_status_display(),
        "irn": e.irn,
        "ack_no": e.ack_no,
        "ack_date": e.ack_date.isoformat() if e.ack_date else "",
        "eway_bill_no": e.eway_bill_no,
        "eway_bill_date": e.eway_bill_date.isoformat() if e.eway_bill_date else "",
        "valid_upto": e.valid_upto.isoformat() if e.valid_upto else "",
        "transporter_gstin": eff["transporter_gstin"],
        "transporter_name": eff["transporter_name"],
        "transport_mode": eff["transport_mode"],
        "transport_doc_no": eff["transport_doc_no"],
        "transport_doc_date": eff["transport_doc_date"].isoformat() if eff["transport_doc_date"] else "",
        "vehicle_no": eff["vehicle_no"],
        "distance_km": eff["distance_km"],
        "recipient_pincode": eff["recipient_pincode"],
        "last_error": e.last_error,
        "provider": e.provider,
        "environment": e.environment,
    }


def validate(invoice, e):
    """Mandatory-field validation before a generation request is even
    attempted -- never guesses a missing value, only reports it."""
    errors = []
    if not invoice["items"]:
        errors.append("The invoice has no items.")
    for i, line in enumerate(invoice["items"], start=1):
        if not line.get("hsn_code"):
            errors.append(f"Item row {i}: HSN code is missing.")
    is_cash = not invoice.get("party_code")
    if is_cash:
        if not invoice.get("cash_party_name"):
            errors.append("Cash party name is missing.")
    else:
        if not invoice.get("gst_no"):
            errors.append("Party GSTIN is missing (required for an e-way bill / e-invoice).")
        if not invoice.get("party_state_code"):
            errors.append("Party state code is missing.")
    eff = effective_transport(invoice, e)
    if not eff["recipient_pincode"]:
        errors.append("Recipient PIN code is missing on the Party Master -- add it there before generating.")
    if not eff["vehicle_no"]:
        errors.append("Vehicle number is missing on the invoice.")
    if not eff["transport_mode"]:
        errors.append("Transport mode is missing.")
    if not eff["distance_km"]:
        errors.append("Approximate distance (km) is missing.")
    return errors


@transaction.atomic
def save_transport_details(bill_no, data, username):
    """Saves/updates the transport + recipient-pincode fields an operator
    enters before generation (none of these exist on the legacy schema)."""
    e, _ = EwayBill.objects.select_for_update().get_or_create(bill_no=bill_no)
    for field in ("transporter_gstin", "transporter_name", "transport_mode",
                  "transport_doc_no", "vehicle_no", "recipient_pincode"):
        if field in data:
            setattr(e, field, (data.get(field) or "").strip())
    if "distance_km" in data:
        try:
            e.distance_km = int(data["distance_km"]) if data["distance_km"] not in (None, "") else None
        except (TypeError, ValueError):
            raise EwayBillError("Distance must be a whole number of kilometres.")
    if data.get("transport_doc_date"):
        try:
            e.transport_doc_date = datetime.strptime(data["transport_doc_date"], "%Y-%m-%d").date()
        except ValueError:
            raise EwayBillError("Invalid transport document date.")
    e.save()
    return e


def build_einvoice_payload(invoice, e):
    """Maps this app's existing GST invoice data onto the standard government
    e-Invoice schema (the shape most GSPs, Chartered Info included, expect on
    their 'Invoice' endpoint). ASSUMPTION: field names/structure follow the
    published CBIC e-invoice schema v1.1 -- confirm against Chartered Info's
    own sample payloads before first live use; this is the one place to adjust
    if their exact key names differ."""
    cfg = provider.config()
    eff = effective_transport(invoice, e)
    supply_type = (invoice.get("supply_type") or "W").upper()
    interstate = supply_type == "I"

    items = []
    taxable_total = Decimal("0")
    for i, line in enumerate(invoice["items"], start=1):
        amount = _d(line["amount"])
        gst_pct = _d(line["gst_pct"])
        gst_amt = (amount * gst_pct / 100).quantize(Decimal("0.01"))
        taxable_total += amount
        item = {
            "SlNo": str(i),
            "PrdDesc": line["item_name"] or line["item_code"],
            "HsnCd": line["hsn_code"],
            "Qty": line["qty"],
            "Unit": line.get("unit") or "NOS",
            "UnitPrice": line["rate"],
            "TotAmt": f"{amount:.2f}",
            "AssAmt": f"{amount:.2f}",
            "GstRt": f"{gst_pct:.2f}",
            "TotItemVal": f"{(amount + gst_amt):.2f}",
        }
        if interstate:
            item["IgstAmt"] = f"{gst_amt:.2f}"
        else:
            item["CgstAmt"] = f"{(gst_amt / 2):.2f}"
            item["SgstAmt"] = f"{(gst_amt / 2):.2f}"
        items.append(item)

    gst_total = _d(invoice["gst_amount"])
    return {
        "Version": "1.1",
        "TranDtls": {"TaxSch": "GST", "SupTyp": "B2B" if invoice.get("party_code") else "B2C"},
        "DocDtls": {"Typ": "INV", "No": invoice["bill_no"], "Dt": _ddmmyyyy(invoice["date"])},
        "SellerDtls": {
            "Gstin": cfg["company_gstin"],
            "LglNm": settings.BRAND["name"],
            "Addr1": settings.BRAND.get("address_line1", ""),
            "Loc": settings.BRAND.get("address_line2", ""),
            "Pin": cfg.get("company_pin", ""),
            "Stcd": cfg.get("company_state_code", ""),
        },
        "BuyerDtls": {
            "Gstin": invoice.get("gst_no") or "",
            "LglNm": invoice.get("party_name") or invoice.get("cash_party_name") or "",
            "Addr1": invoice.get("party_address") or "",
            "Loc": invoice.get("city") or invoice.get("cash_party_city") or "",
            "Pin": eff["recipient_pincode"],
            "Stcd": invoice.get("party_state_code") or "",
            "Pos": invoice.get("party_state_code") or "",
        },
        "ItemList": items,
        "ValDtls": {
            "AssVal": f"{taxable_total:.2f}",
            "TotInvVal": invoice["net_amount"],
            "GstAmt": f"{gst_total:.2f}",
        },
    }


def _ddmmyyyy(iso_date):
    try:
        y, m, d = str(iso_date).split("-")
        return f"{d}/{m}/{y}"
    except ValueError:
        return ""


@transaction.atomic
def generate(bill_no, username):
    """Runs the real generation workflow: validate -> (IRN if not already
    issued) -> E-Way Bill by IRN -> persist status/response. Never marks a
    bill Generated unless the provider itself confirms it; idempotent -- a
    bill that's already Generated is refused outright (step 12/duplicate
    prevention), and select_for_update() blocks a second concurrent request
    on the same bill_no until the first one finishes."""
    invoice = gi_services.get_invoice(bill_no)
    if not invoice:
        raise EwayBillError("GST invoice not found.")

    e, _ = EwayBill.objects.select_for_update().get_or_create(bill_no=bill_no)
    if e.status == EwayBill.STATUS_GENERATED:
        raise EwayBillError("An E-Way Bill has already been generated for this invoice.")

    errors = validate(invoice, e)
    if errors:
        raise EwayBillError("Fix the highlighted items before generating.", {"fields": errors})

    e.status = EwayBill.STATUS_PENDING
    e.save(update_fields=["status", "updated_at"])

    try:
        if not e.irn:
            payload = build_einvoice_payload(invoice, e)
            e.last_request = str(payload)[:4000]
            irn_data = provider.generate_irn(payload, eway_bill=e)
            e.irn = irn_data.get("Irn") or irn_data.get("IRN") or ""
            e.ack_no = str(irn_data.get("AckNo") or "")
            ack_dt = irn_data.get("AckDt")
            e.ack_date = _parse_dt(ack_dt)
            e.signed_qr_code = irn_data.get("SignedQRCode") or ""
            if not e.irn:
                raise ProviderError("Provider did not return an IRN.", raw=irn_data)

        eff = effective_transport(invoice, e)
        eway_data = provider.generate_eway_by_irn(e.irn, {
            "transport_mode": eff["transport_mode"],
            "transporter_gstin": eff["transporter_gstin"],
            "transporter_name": eff["transporter_name"],
            "transport_doc_no": eff["transport_doc_no"],
            "transport_doc_date": eff["transport_doc_date"].isoformat() if eff["transport_doc_date"] else "",
            "vehicle_no": eff["vehicle_no"],
            "distance_km": eff["distance_km"],
        }, eway_bill=e)

        e.eway_bill_no = str(eway_data.get("EwbNo") or "")
        e.eway_bill_date = _parse_dt(eway_data.get("EwbDt")) or timezone.now()
        e.valid_upto = _parse_dt(eway_data.get("EwbValidTill"))
        e.last_response = str(eway_data)[:4000]
        e.status = EwayBill.STATUS_GENERATED
        e.last_error = ""
        e.generated_by = username
        e.save()
        return e
    except ProviderError as exc:
        e.status = EwayBill.STATUS_FAILED
        e.last_error = str(exc)
        if exc.raw:
            e.last_response = str(exc.raw)[:4000]
        e.save()
        raise EwayBillError(str(exc)) from exc


def _parse_dt(value):
    if not value:
        return None
    from django.utils.dateparse import parse_datetime
    dt = parse_datetime(str(value))
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt

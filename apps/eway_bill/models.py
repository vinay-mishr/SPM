from django.db import models


class EwayBill(models.Model):
    """
    E-Way Bill tracking for a GST Invoice (apps.gst_invoice, ``bill`` table,
    bill_type='G'). The invoice header/items/party themselves are NOT duplicated
    here -- this table only tracks the e-way-bill-specific workflow for a given
    ``bill_no`` (same loose-reference convention apps.gst_invoice.models
    .GstInvoiceExtra already uses: the legacy ``bill`` row, found by bill_no,
    stays the header of record).

    Kept deliberately separate from GstInvoiceExtra.eway_no/eway_date, which are
    plain operator-typed fields with no provider behind them -- this table is
    for the real, provider-confirmed E-Way Bill (number, ack, validity, status)
    and is never written to on a guess; see services.generate().
    """

    STATUS_NOT_GENERATED = "NOT_GENERATED"
    STATUS_PENDING = "PENDING"
    STATUS_GENERATED = "GENERATED"
    STATUS_FAILED = "FAILED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_NOT_GENERATED, "Not Generated"),
        (STATUS_PENDING, "Pending"),
        (STATUS_GENERATED, "Generated"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    TRANSPORT_MODE_CHOICES = [
        ("1", "Road"),
        ("2", "Rail"),
        ("3", "Air"),
        ("4", "Ship"),
    ]

    bill_no = models.CharField("GST bill no", max_length=10, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_GENERATED)

    # -- e-Invoice (IRN) response, needed before an e-way bill can be generated
    # by IRN against EINV_EWAYBILL_URL (see provider.py) --
    irn = models.CharField("IRN", max_length=64, blank=True)
    ack_no = models.CharField("acknowledgement no", max_length=20, blank=True)
    ack_date = models.DateTimeField(null=True, blank=True)
    signed_qr_code = models.TextField(blank=True)

    # -- e-Way Bill response --
    eway_bill_no = models.CharField("e-way bill no", max_length=20, blank=True)
    eway_bill_date = models.DateTimeField(null=True, blank=True)
    valid_upto = models.DateTimeField(null=True, blank=True)

    provider = models.CharField(max_length=30, default="charteredinfo")
    environment = models.CharField(max_length=10, default="sandbox")

    # -- Transport details. None of these exist on the legacy ``bill`` row
    # except vehicle_no/transport (already shown on the GST Invoice form itself,
    # read-only here) -- the rest must be entered per-bill before generation. --
    transporter_gstin = models.CharField(max_length=15, blank=True)
    transporter_name = models.CharField(max_length=100, blank=True)
    transport_mode = models.CharField(max_length=1, choices=TRANSPORT_MODE_CHOICES, blank=True)
    transport_doc_no = models.CharField(max_length=20, blank=True)
    transport_doc_date = models.DateField(null=True, blank=True)
    vehicle_no = models.CharField(max_length=20, blank=True)
    distance_km = models.PositiveIntegerField(null=True, blank=True)

    # Not stored anywhere on cust_mst (the party master has no PIN code column
    # at all, confirmed by repo-wide search) -- mandatory on the government
    # e-invoice/e-way schema, so it's entered here per-bill instead of guessed.
    recipient_pincode = models.CharField(max_length=6, blank=True)

    last_error = models.TextField(blank=True)
    last_request = models.TextField(blank=True)
    last_response = models.TextField(blank=True)

    generated_by = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "E-Way Bill"

    def __str__(self):
        return self.bill_no


class EwayBillLog(models.Model):
    """One row per provider API call (auth / irn / eway / cancel), for audit and
    troubleshooting -- request/response bodies have credentials stripped before
    being written (see provider.py's _redact())."""

    eway_bill = models.ForeignKey(EwayBill, related_name="logs", on_delete=models.CASCADE)
    action = models.CharField(max_length=20)
    request_payload = models.TextField(blank=True)
    response_payload = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "E-Way Bill API log"


class EwayAuthToken(models.Model):
    """Cached provider auth token (one row per provider), so every invoice
    generation doesn't re-authenticate. Expiry-checked in provider.get_token()."""

    provider = models.CharField(max_length=30, unique=True)
    token = models.TextField()
    sek = models.TextField(blank=True)
    expires_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "E-Way Bill provider token"

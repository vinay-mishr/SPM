"""
Thin HTTP client for the Chartered Information Systems e-Invoice / E-Way Bill
API (``EINV_*`` settings in .env -- see EWAY_BILL_PROVIDER in
config.settings.base). Credentials are already live in this project's .env;
the integration code calling them did not exist anywhere in the repo before
this module, so the exact request/response shapes below are the standard
NIC-IRP-style contract most GSPs (Chartered Info included) resell access to --
clearly flagged with ASSUMPTION comments wherever unverified. Nothing in this
file ever reports success without the provider's own confirmation; a shape
mismatch raises ProviderError with the provider's raw response rather than
guessing.

Three real calls, matching the distinct endpoints already in .env:
  * get_token()           -- EINV_AUTH_URL
  * generate_irn()         -- EINV_INVOICE_URL (e-Invoice / IRN)
  * generate_eway_by_irn() -- EINV_EWAYBILL_URL ("Generate E-Way Bill by IRN";
    per the project's own .env comment, a DIFFERENT contract from the above:
    its own query params incl. action=GENEWAYBILL, no {Status,Data} envelope)
"""
import json
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import EwayAuthToken, EwayBillLog

logger = logging.getLogger("eway_bill")

TIMEOUT = 20
_REDACT_KEYS = {"password", "Password", "password2", "app_key", "AppKey", "AppKeyPassword",
                "Sek", "sek", "AuthToken", "token", "Authorization"}


class ProviderError(Exception):
    """Raised on any failure talking to the provider -- network, HTTP, or a
    provider-reported business error. Always carries the provider's own
    message/body (``raw``) so the caller can show it verbatim; never raised
    to mean "assume success"."""

    def __init__(self, message, raw=None):
        super().__init__(message)
        self.raw = raw


def _redact(payload):
    if not isinstance(payload, dict):
        return payload
    return {k: ("***redacted***" if k in _REDACT_KEYS else v) for k, v in payload.items()}


def _dump(payload):
    try:
        return json.dumps(_redact(payload), default=str)[:4000]
    except (TypeError, ValueError):
        return str(payload)[:4000]


def _looks_like_stale_token(message):
    text = (message or "").lower()
    return "authtoken" in text and ("expired" in text or "not found" in text)


def _call_with_token_retry(make_request):
    """Runs make_request(token) once; if the provider reports the token as
    stale, clears the cached one and retries with a freshly-issued token.

    Confirmed live (2026-10-21): this provider's real token lifetime is
    shorter than the TokenExpiry value in its own auth response, so a cached
    token can look valid by our stored expiry and still be rejected by
    another endpoint moments later ("AuthToken not found or expired")."""
    token = get_token()
    try:
        return make_request(token)
    except ProviderError as exc:
        if not _looks_like_stale_token(str(exc)):
            raise
        EwayAuthToken.objects.filter(provider=config()["provider"]).delete()
        token = get_token(force=True)
        return make_request(token)


def _log(eway_bill, action, request_payload, response_payload, success):
    if eway_bill is not None and eway_bill.pk:
        EwayBillLog.objects.create(
            eway_bill=eway_bill, action=action,
            request_payload=_dump(request_payload), response_payload=_dump(response_payload),
            success=success,
        )
    logger.info("eway_bill provider call action=%s success=%s", action, success)


def config():
    cfg = getattr(settings, "EWAY_BILL_PROVIDER", {}) or {}
    required = ("asp_id", "asp_password", "gst_username", "gst_password", "company_gstin",
                "auth_url", "invoice_url", "eway_url")
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise ProviderError(
            "E-Way Bill provider isn't configured (missing: " + ", ".join(missing) + "). "
            "Set the EINV_* variables in .env before generating."
        )
    return cfg


def _post(url, headers=None, json_body=None, params=None):
    try:
        resp = requests.post(url, headers=headers, json=json_body, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ProviderError(f"Could not reach the e-way bill provider: {exc}") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {"raw_text": resp.text[:2000]}
    if resp.status_code >= 400:
        raise ProviderError(
            f"Provider returned HTTP {resp.status_code}: {_error_message(body) or body}",
            raw=body,
        )
    return body


def _get(url, headers=None, params=None):
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ProviderError(f"Could not reach the e-way bill provider: {exc}") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {"raw_text": resp.text[:2000]}
    if resp.status_code >= 400:
        raise ProviderError(
            f"Provider returned HTTP {resp.status_code}: {_error_message(body) or body}",
            raw=body,
        )
    return body


def _parse_expiry(value):
    if not value:
        return None
    dt = parse_datetime(str(value))
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _ok(body):
    return str(body.get("Status", "")).strip().lower() in {"1", "true"}


def _error_message(body):
    """Pulls a human-readable error out of whichever envelope the provider used
    -- confirmed live (2026-10-21) that different endpoints on this same
    provider use different shapes: {status_cd, error: {error_cd, message}}
    (the GSP-gateway-level errors, e.g. missing aspid/gstin), and the real NIC
    e-invoice {Status, ErrorDetails: [{ErrorCode, ErrorMessage}]} (errors from
    the GST portal itself, e.g. a bad username/password)."""
    error = body.get("error")
    if isinstance(error, dict) and error.get("message"):
        return error["message"]
    details = body.get("ErrorDetails")
    if isinstance(details, list) and details:
        first = details[0]
        if isinstance(first, dict):
            return first.get("ErrorMessage") or first.get("error_msg") or str(first)
        return str(first)
    if isinstance(details, str):
        return details
    return body.get("message") or ""


def get_token(force=False):
    """Returns a valid bearer token, authenticating only when there's no
    cached token or it's within 2 minutes of expiry.

    Confirmed live (2026-10-21) against the real endpoint -- NOT the generic
    NIC-IRP contract originally assumed:
      * GET, not POST (the server itself replies 405 Allow: GET to a POST).
      * Query params aspid, Gstin, User_Name, eInvPwd (the GST portal
        password, cfg['gst_password']) and password (the ASP's OWN password,
        cfg['asp_password'] -- distinct from eInvPwd/GST password).
      * .env's EINV_ASP_PASSWORD is URL-encoded (e.g. "ctc%231403") and must be
        decoded to its literal form ("ctc#1403") before use here -- `requests`
        re-encodes it correctly when building the query string itself.
      * Response envelope is the real NIC e-invoice shape:
        {Status, Data, ErrorDetails: [{ErrorCode, ErrorMessage}], InfoDtls}.
    """
    cfg = config()
    cached = EwayAuthToken.objects.filter(provider=cfg["provider"]).first()
    if cached and not force and cached.expires_at > timezone.now() + timedelta(minutes=2):
        return cached.token

    from urllib.parse import unquote
    params = {
        "aspid": cfg["asp_id"],
        "Gstin": cfg["company_gstin"],
        "User_Name": cfg["gst_username"],
        "eInvPwd": cfg["gst_password"],
        "password": unquote(cfg["asp_password"]),
    }
    body = _get(cfg["auth_url"], params=params)
    success = _ok(body) and not body.get("ErrorDetails")
    _log(None, "AUTH", {k: v for k, v in params.items() if k not in ("eInvPwd", "password")}, body, success=success)
    if not success:
        raise ProviderError(
            _error_message(body) or "Authentication with the e-way bill provider failed.",
            raw=body,
        )
    data = body.get("Data") or body
    token = data.get("AuthToken") or data.get("Token") or data.get("auth_token")
    if not token:
        raise ProviderError("Provider did not return an auth token.", raw=body)
    expires_at = _parse_expiry(data.get("TokenExpiry") or data.get("Expiry")) or (timezone.now() + timedelta(hours=6))
    EwayAuthToken.objects.update_or_create(
        provider=cfg["provider"],
        defaults={"token": token, "sek": data.get("Sek", ""), "expires_at": expires_at},
    )
    return token


def get_cached_token_record():
    """The cached EwayAuthToken row (if any) for the configured provider -- used
    by views.eb_token to report expiry without re-authenticating."""
    cfg = getattr(settings, "EWAY_BILL_PROVIDER", {}) or {}
    name = cfg.get("provider")
    return EwayAuthToken.objects.filter(provider=name).first() if name else None


def generate_irn(invoice_payload, eway_bill=None):
    """Generates the e-Invoice (IRN). ``invoice_payload`` must already be in the
    government e-invoice schema shape (see services.build_einvoice_payload).
    Returns the provider's Data dict (Irn, AckNo, AckDt, SignedQRCode, ...)."""
    cfg = config()

    def make_request(token):
        # Same "aspid" requirement confirmed live on the auth/GSTIN-lookup
        # calls -- applied consistently here too (adjust if this endpoint
        # turns out not to need it once actually exercised).
        headers = {
            "Authorization": f"Bearer {token}", "Gstin": cfg["company_gstin"],
            "Content-Type": "application/json", "aspid": cfg["asp_id"],
        }
        body = _post(cfg["invoice_url"], headers=headers, json_body=invoice_payload, params={"aspid": cfg["asp_id"]})
        success = _ok(body) and not isinstance(body.get("error"), dict)
        _log(eway_bill, "IRN", invoice_payload, body, success=success)
        if not success:
            raise ProviderError(
                _error_message(body) or "The provider rejected the e-invoice request.",
                raw=body,
            )
        return body.get("Data") or body

    return _call_with_token_retry(make_request)


def generate_eway_by_irn(irn, transport, eway_bill=None):
    """Generates the E-Way Bill for an already-issued IRN.

    ASSUMPTION (unverified -- confirm against Chartered Info's docs before live
    use): per this project's own .env comment, this endpoint's contract is NOT
    the same {Status,Data} envelope as auth/IRN -- a successful call is assumed
    to return EwbNo/EwbDt/EwbValidTill directly; an unsuccessful one an
    ErrorDetails/error/message field instead. Adjust the body/response parsing
    here (only) once the real contract is confirmed.
    """
    cfg = config()
    payload = {
        "Irn": irn,
        "TransMode": transport.get("transport_mode") or "",
        "TransId": transport.get("transporter_gstin") or "",
        "TransName": transport.get("transporter_name") or "",
        "TransDocNo": transport.get("transport_doc_no") or "",
        "TransDocDate": transport.get("transport_doc_date") or "",
        "VehNo": transport.get("vehicle_no") or "",
        "Distance": transport.get("distance_km") or 0,
    }

    def make_request(token):
        headers = {
            "Authorization": f"Bearer {token}", "Gstin": cfg["company_gstin"],
            "Content-Type": "application/json", "aspid": cfg["asp_id"],
        }
        body = _post(cfg["eway_url"], headers=headers, json_body=payload,
                     params={"action": "GENEWAYBILL", "aspid": cfg["asp_id"]})
        success = bool(body.get("EwbNo")) and not (body.get("ErrorDetails") or body.get("error"))
        _log(eway_bill, "EWAYBILL", payload, body, success=success)
        if not success:
            raise ProviderError(
                _error_message(body) or "The provider did not return an e-way bill number.",
                raw=body,
            )
        return body

    return _call_with_token_retry(make_request)


def lookup_gstin(gstin):
    """'Get GSTIN Details' -- per the project's own .env comment, this is the
    one endpoint that's actually been live-confirmed (2026-09-11, against SP
    Machines' own GSTIN), same eivital module/auth as get_token(). Returns the
    provider's raw Data dict (field names not normalised here -- callers pick
    out only the keys they recognise and leave the rest alone) or raises
    ProviderError; never fabricates a result for an invalid/unknown GSTIN."""
    cfg = getattr(settings, "EWAY_BILL_PROVIDER", {}) or {}
    if not cfg.get("gstin_details_url"):
        raise ProviderError("GSTIN lookup isn't configured (EINV_GSTIN_DETAILS_URL is not set).")

    from urllib.parse import unquote

    def make_request(token):
        # Same "eivital" module as the auth call (per the project's own .env
        # comment) -- confirmed live (2026-10-21) that it wants the identical
        # full credential param set as get_token(), not just a bearer token.
        params = {
            "aspid": cfg.get("asp_id", ""),
            "Gstin": cfg.get("company_gstin", ""),
            "User_Name": cfg.get("gst_username", ""),
            "AuthToken": token,
            "password": unquote(cfg.get("asp_password", "")),
        }
        headers = {"Authorization": f"Bearer {token}"}
        url = cfg["gstin_details_url"].rstrip("/") + "/" + gstin
        body = _get(url, headers=headers, params=params)
        error = body.get("error") if isinstance(body.get("error"), dict) else None
        data = body.get("Data") if isinstance(body, dict) else body
        # Confirmed live (2026-10-21): "Data" comes back as a JSON-encoded
        # STRING (e.g. '{"Gstin":"...","TradeName":"...","LegalName":"...",
        # ...}'), not a nested object -- needs a second json.loads().
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                data = None
        success = not error and isinstance(data, dict) and bool(data.get("Gstin") or data.get("LegalName"))
        _log(None, "GSTIN_LOOKUP", {"gstin": gstin}, body, success=success)
        if not success:
            raise ProviderError(
                (error or {}).get("message") or body.get("ErrorDetails") or body.get("message")
                or f"No GST details found for {gstin}.",
                raw=body,
            )
        return data

    return _call_with_token_retry(make_request)

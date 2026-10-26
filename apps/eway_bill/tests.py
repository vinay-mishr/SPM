from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import provider
from .models import EwayAuthToken, EwayBill
from .provider import ProviderError
from .services import effective_transport, validate

User = get_user_model()


class ValidateTests(TestCase):
    """validate() works against a plain dict shaped like
    apps.gst_invoice.services.get_invoice()'s output -- no DB/legacy connection
    needed, so these run without the legacy SQL Server reachable."""

    def _invoice(self, **overrides):
        base = {
            "items": [{"hsn_code": "8479"}],
            "party_code": "C001", "gst_no": "03ABCDE1234F1Z5",
            "party_state_code": "03", "cash_party_name": "", "vehicle_no": "PB65AB1234",
        }
        base.update(overrides)
        return base

    def test_missing_items_reported(self):
        errors = validate(self._invoice(items=[]), None)
        self.assertIn("The invoice has no items.", errors)

    def test_missing_hsn_reported(self):
        errors = validate(self._invoice(items=[{"hsn_code": ""}]), None)
        self.assertTrue(any("HSN code is missing" in e for e in errors))

    def test_missing_gstin_for_non_cash_party(self):
        errors = validate(self._invoice(gst_no=""), None)
        self.assertTrue(any("GSTIN is missing" in e for e in errors))

    def test_cash_party_does_not_require_gstin(self):
        errors = validate(self._invoice(party_code="", gst_no="", cash_party_name="Walk-in"), None)
        self.assertFalse(any("GSTIN is missing" in e for e in errors))

    def test_complete_invoice_with_eway_row_has_no_errors(self):
        e = EwayBill(
            bill_no="39", recipient_pincode="160055", transport_mode="1",
            distance_km=25, vehicle_no="PB65AB1234",
        )
        errors = validate(self._invoice(), e)
        self.assertEqual(errors, [])

    def test_recipient_pin_and_vehicle_auto_fetched_from_invoice_without_eway_row(self):
        # No EwayBill row saved at all (e=None) -- pin/vehicle still resolve
        # straight from the party/invoice data, with no manual entry needed.
        invoice = self._invoice(party_pin="160055", vehicle_no="PB65AB1234", party_transport="ABC TRANSPORT")
        eff = effective_transport(invoice, None)
        self.assertEqual(eff["recipient_pincode"], "160055")
        self.assertEqual(eff["vehicle_no"], "PB65AB1234")
        self.assertEqual(eff["transporter_name"], "ABC TRANSPORT")

    def test_manual_eway_row_value_overrides_database_value(self):
        e = EwayBill(bill_no="39", recipient_pincode="110001")
        invoice = self._invoice(party_pin="160055")
        eff = effective_transport(invoice, e)
        self.assertEqual(eff["recipient_pincode"], "110001")


class ProviderConfigTests(TestCase):
    @override_settings(EWAY_BILL_PROVIDER={})
    def test_missing_config_raises_clear_error(self):
        with self.assertRaises(ProviderError) as ctx:
            provider.config()
        self.assertIn("isn't configured", str(ctx.exception).lower())

    def test_configured_env_is_picked_up_from_settings(self):
        # Exercises the real settings wiring (EWAY_BILL_PROVIDER built from the
        # EINV_* env vars already in .env) without making a network call.
        cfg = provider.config()
        self.assertEqual(cfg["provider"], "charteredinfo")
        self.assertTrue(cfg["company_gstin"])


class TokenViewTests(TestCase):
    """eb_token never fabricates a token -- success only comes from
    provider.get_token() actually returning one; network calls are mocked so
    these run without reaching the real provider."""

    def setUp(self):
        self.user = User.objects.create_user(username="eb_tester", password="x")
        self.client.force_login(self.user)
        self.url = reverse("eway_bill:api_token")

    @override_settings(LEGACY_WRITES_ENABLED=False)
    def test_forbidden_without_edit_permission(self):
        res = self.client.post(self.url, content_type="application/json")
        self.assertEqual(res.status_code, 403)

    @override_settings(EWAY_BILL_PROVIDER={})
    def test_missing_config_reports_clear_error_not_a_fake_token(self):
        res = self.client.post(self.url, content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("isn't configured", res.json()["message"].lower())
        self.assertNotIn("token", res.json())

    @patch("apps.eway_bill.provider._get")
    def test_successful_auth_returns_token_and_expiry(self, mock_get):
        mock_get.return_value = {
            "Status": "1",
            "Data": {"AuthToken": "abcd1234efgh5678", "TokenExpiry": "", "Sek": "whatever"},
        }
        res = self.client.post(self.url, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["token"], "abcd1234efgh5678")
        self.assertTrue(body["expires_at"])
        # Cached for reuse -- a second call within validity must not re-auth.
        self.assertEqual(EwayAuthToken.objects.count(), 1)
        mock_get.reset_mock()
        res2 = self.client.post(self.url, content_type="application/json")
        self.assertEqual(res2.status_code, 200)
        mock_get.assert_not_called()

    @patch("apps.eway_bill.provider._get")
    def test_provider_failure_surfaces_real_error(self, mock_get):
        mock_get.return_value = {"Status": "0", "ErrorDetails": [{"ErrorCode": "1017", "ErrorMessage": "Invalid GST credentials"}]}
        res = self.client.post(self.url, content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid GST credentials", res.json()["message"])

    def test_cached_but_expired_token_is_refreshed(self):
        cfg = provider.config()
        EwayAuthToken.objects.create(
            provider=cfg["provider"], token="stale-token",
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        with patch("apps.eway_bill.provider._get") as mock_get:
            mock_get.return_value = {"Status": "1", "Data": {"AuthToken": "fresh-token"}}
            res = self.client.post(self.url, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["token"], "fresh-token")


class GstinLookupProviderTests(TestCase):
    """provider.lookup_gstin() -- confirmed live (2026-10-21) that this
    endpoint's "Data" comes back as a JSON-encoded STRING, not a nested
    object, so it needs its own second json.loads()."""

    @patch("apps.eway_bill.provider.get_token", return_value="fake-token")
    @patch("apps.eway_bill.provider._get")
    def test_double_encoded_data_string_is_parsed(self, mock_get, mock_token):
        mock_get.return_value = {
            "Status": "1",
            "Data": '{"Gstin":"03AHJPC2414N1ZN","LegalName":"RIMPAL  CHADHA","AddrPncd":160059}',
        }
        data = provider.lookup_gstin("03AHJPC2414N1ZN")
        self.assertEqual(data["LegalName"], "RIMPAL  CHADHA")
        self.assertEqual(data["AddrPncd"], 160059)

    @patch("apps.eway_bill.provider.get_token", return_value="fake-token")
    @patch("apps.eway_bill.provider._get")
    def test_malformed_data_string_raises_not_a_blank_result(self, mock_get, mock_token):
        mock_get.return_value = {"Status": "1", "Data": "not valid json"}
        with self.assertRaises(ProviderError):
            provider.lookup_gstin("03AHJPC2414N1ZN")


class ModelTests(TestCase):
    def test_default_status_is_not_generated(self):
        e = EwayBill.objects.create(bill_no="999")
        self.assertEqual(e.status, EwayBill.STATUS_NOT_GENERATED)
        self.assertEqual(str(e), "999")

    def test_bill_no_is_unique(self):
        EwayBill.objects.create(bill_no="1000")
        with self.assertRaises(Exception):
            EwayBill.objects.create(bill_no="1000")

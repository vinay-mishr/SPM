import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.gl.models import Ledger

from . import services
from .models import GstRate


class GstTableMixin:
    """gst and gled_mst are the old software's tables (unmanaged); tests create them."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(GstRate)
            editor.create_model(Ledger)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(Ledger)
            editor.delete_model(GstRate)


class GstMasterTests(GstTableMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_user(username="gst_editor", password="S3cure-pass!")
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_gst_master"))
        cls.viewer = get_user_model().objects.create_user(username="gst_viewer", password="S3cure-pass!")

    def setUp(self):
        Ledger.objects.create(ledger_code="G019", description="SALE TAXFREE A/C")
        Ledger.objects.create(ledger_code="G020", description="SALE A/C")
        Ledger.objects.create(ledger_code="G024", description="SALE CGST A/C")

    def save(self, mode, rate, fields=None, as_user=None):
        self.client.force_login(as_user or self.editor)
        payload = {"mode": mode, "rate": rate}
        payload.update(fields or {})
        return self.client.post(
            reverse("gst:api_save"), data=json.dumps(payload), content_type="application/json",
        )

    def check(self, rate):
        self.client.force_login(self.editor)
        return self.client.get(reverse("gst:api_check"), {"rate": rate})

    def test_page_loads(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("gst:master"))
        self.assertContains(response, "GST %")

    def test_check_reports_not_found(self):
        response = self.check("18")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["exists"])

    def test_add_creates_rate(self):
        response = self.save("add", "5", {"sale_taxfree_account": "g019", "sale_account": "g020"})
        self.assertEqual(response.status_code, 200, response.content)
        rate = GstRate.objects.get(rate=Decimal("5.00"))
        self.assertEqual(rate.sale_taxfree_account, "G019")
        self.assertEqual(rate.sale_account, "G020")

    def test_add_duplicate_rejected(self):
        self.save("add", "5")
        response = self.save("add", "5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("GST Rate Already Defined", response.json()["errors"]["rate"])
        self.assertEqual(GstRate.objects.count(), 1)

    def test_check_reports_found_after_add(self):
        self.save("add", "5")
        response = self.check("5")
        self.assertTrue(response.json()["exists"])
        self.assertEqual(response.json()["data"]["rate"], "5.00")

    def test_modify_updates_existing_rate(self):
        self.save("add", "5", {"sale_account": "G020"})
        response = self.save("modify", "5", {"sale_account": "G019"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(GstRate.objects.get(rate=Decimal("5.00")).sale_account, "G019")

    def test_modify_unknown_rate_rejected(self):
        response = self.save("modify", "28", {"sale_account": "G020"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("GST Rate Not Defined", response.json()["errors"]["rate"])

    def test_unknown_ledger_code_rejected(self):
        response = self.save("add", "5", {"sale_account": "ZZZZ"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("ZZZZ", response.json()["errors"]["sale_account"])
        self.assertFalse(GstRate.objects.exists())

    def test_blank_rate_rejected(self):
        response = self.save("add", "")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GstRate.objects.exists())

    def test_negative_rate_rejected(self):
        response = self.save("add", "-5")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GstRate.objects.exists())

    def test_viewer_without_permission_cannot_save(self):
        response = self.save("add", "5", as_user=self.viewer)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(GstRate.objects.exists())

    def test_writes_disabled_blocks_save(self):
        from unittest import mock
        with mock.patch.object(services, "writes_enabled", return_value=False):
            response = self.save("add", "5")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(GstRate.objects.exists())

    def test_login_required(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("gst:master")).status_code, 200)

    def test_master_page_lists_existing_rates(self):
        self.save("add", "5")
        self.save("add", "12")
        self.client.force_login(self.editor)
        response = self.client.get(reverse("gst:master"))
        rates = [r["rate"] for r in response.context["initial_data"]["rates"]]
        self.assertEqual(rates, ["5.00", "12.00"])

    def test_delete_removes_rate(self):
        self.save("add", "5")
        self.client.force_login(self.editor)
        response = self.client.post(reverse("gst:api_delete", args=["5"]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(GstRate.objects.filter(rate=Decimal("5.00")).exists())

    def test_delete_unknown_rate_rejected(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse("gst:api_delete", args=["28"]))
        self.assertEqual(response.status_code, 409)

    def test_delete_requires_permission(self):
        self.save("add", "5")
        self.client.force_login(self.viewer)
        response = self.client.post(reverse("gst:api_delete", args=["5"]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(GstRate.objects.filter(rate=Decimal("5.00")).exists())

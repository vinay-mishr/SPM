from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import Item


class ItemMasterTests(TestCase):
    """Item is an unmanaged model (the old software's table), so tests create it themselves."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Item)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(Item)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="operator", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)

    def post_item(self, url=None, **overrides):
        data = {
            "item_name_1": "  Flow Wrap Machine  ",
            "item_name_2": "SP200",
            "item_name_3": "",
            "unit": "nos",
            "hsn_code": "84224000",
            "gst_percent": "18",
            "rate": "600000.00",
            "opening_balance": "0",
        }
        data.update(overrides)
        return self.client.post(url or reverse("items:api_create"), data)

    def test_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("items:master"))
        self.assertEqual(response.status_code, 302)

    def test_page_renders_with_sidebar_link(self):
        response = self.client.get(reverse("items:master"))
        self.assertContains(response, "Item Master")
        self.assertContains(response, 'data-action="add"')
        for heading in ("Code", "Item Description", "Description", "Rate", "GST %"):
            self.assertContains(response, f">{heading}</th>")
        self.assertNotContains(response, "Op. Balance</th>")
        self.assertContains(response, reverse("items:master"))

    def test_codes_are_sequential_and_zero_padded(self):
        self.assertEqual(services.next_item_code(), "0001")
        self.post_item()
        self.post_item()
        self.assertEqual(list(Item.objects.values_list("item_code", flat=True)), ["0001", "0002"])
        self.assertEqual(services.next_item_code(), "0003")

    def test_create_trims_and_normalises(self):
        response = self.post_item()
        self.assertEqual(response.status_code, 200)
        item = Item.objects.get()
        self.assertEqual(item.item_name_1, "Flow Wrap Machine")
        self.assertEqual(item.unit, "NOS")
        self.assertEqual(item.opening_balance, Decimal("0"))
        self.assertEqual(item.rate, Decimal("600000.00"))

    def test_negative_values_rejected_with_field_errors(self):
        response = self.post_item(gst_percent="-1", rate="-5", opening_balance="-2")
        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        # Opening balance may be negative (the old data has some); GST % and rate may not.
        self.assertEqual(set(errors), {"gst_percent", "rate"})
        self.assertIn("cannot be negative", errors["rate"][0]["message"])
        self.assertFalse(Item.objects.exists())

    def test_gst_above_100_rejected(self):
        response = self.post_item(gst_percent="150")
        self.assertEqual(response.status_code, 400)
        self.assertIn("gst_percent", response.json()["errors"])

    def test_modify_keeps_code(self):
        self.post_item()
        item = Item.objects.get()
        response = self.post_item(
            url=reverse("items:api_update", args=[item.pk]), item_name_1="Updated", rate="1.50"
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.item_code, "0001")
        self.assertEqual(item.item_name_1, "Updated")
        self.assertEqual(Item.objects.count(), 1)

    def test_delete(self):
        self.post_item()
        item = Item.objects.get()
        response = self.client.post(reverse("items:api_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.exists())

    def test_delete_blocked_when_item_in_use(self):
        self.post_item()
        item = Item.objects.get()
        error = ProtectedError("in use", {item})
        with mock.patch.object(Item, "delete", side_effect=error):
            response = self.client.post(reverse("items:api_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("cannot be deleted", response.json()["message"])
        self.assertTrue(Item.objects.exists())

    def test_delete_blocked_when_code_used_in_old_tables(self):
        self.post_item()
        item = Item.objects.get()
        with mock.patch.object(services, "tables_using", return_value=["stock"]):
            response = self.client.post(reverse("items:api_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("used in: stock", response.json()["message"])
        self.assertTrue(Item.objects.exists())

    def test_delete_requires_post(self):
        self.post_item()
        item = Item.objects.get()
        response = self.client.get(reverse("items:api_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 405)


class LegacyReadOnlyTests(TestCase):
    def test_writes_blocked_when_legacy_db_not_enabled(self):
        user = get_user_model().objects.create_user(username="viewer", password="S3cure-pass!")
        self.client.force_login(user)
        with mock.patch.object(services, "writes_enabled", return_value=False):
            response = self.client.post(reverse("items:api_create"), {"item_name_1": "X"})
        self.assertEqual(response.status_code, 403)

    def test_router_sends_item_to_legacy_only_when_configured(self):
        from config.db_routers import LegacyRouter

        router = LegacyRouter()
        self.assertIsNone(router.db_for_read(Item))  # no "legacy" DB in test settings
        with self.settings(DATABASES={"default": {}, "legacy": {}}):
            self.assertEqual(router.db_for_read(Item), "legacy")
            self.assertFalse(router.allow_migrate("legacy", "items"))

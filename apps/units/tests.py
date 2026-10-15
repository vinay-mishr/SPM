from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import Unit


class UnitTableMixin:
    """unit is the old software's table (unmanaged); tests create it themselves."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Unit)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(Unit)


class UnitMasterTests(UnitTableMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="operator", password="S3cure-pass!")
        cls.user.user_permissions.add(Permission.objects.get(codename="change_unit_master"))

    def setUp(self):
        self.client.force_login(self.user)

    def test_grid_shows_reference_column(self):
        Unit.objects.create(name="BOX")
        response = self.client.get(reverse("units:master"))
        self.assertContains(response, "Name")
        units = response.context["initial_data"]["units"]
        self.assertEqual([u["name"] for u in units], ["BOX"])

    def test_add(self):
        response = self.client.post(reverse("units:api_create"), {"name": "box"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Unit.objects.get().name, "BOX")

    def test_duplicate_rejected(self):
        Unit.objects.create(name="BOX")
        response = self.client.post(reverse("units:api_create"), {"name": "box"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.json()["errors"]["name"])
        self.assertEqual(Unit.objects.count(), 1)

    def test_blank_rejected(self):
        response = self.client.post(reverse("units:api_create"), {"name": " "})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Unit.objects.exists())

    def test_too_long_rejected(self):
        response = self.client.post(reverse("units:api_create"), {"name": "TOOLONG"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Unit.objects.exists())

    def test_modify_renames(self):
        Unit.objects.create(name="BOX")
        response = self.client.post(reverse("units:api_update", args=["BOX"]), {"name": "BXS"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(list(Unit.objects.values_list("name", flat=True)), ["BXS"])

    def test_modify_to_existing_name_rejected(self):
        Unit.objects.create(name="BOX")
        Unit.objects.create(name="KG")
        response = self.client.post(reverse("units:api_update", args=["BOX"]), {"name": "kg"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Unit.objects.count(), 2)

    def test_delete(self):
        Unit.objects.create(name="BOX")
        response = self.client.post(reverse("units:api_delete", args=["BOX"]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Unit.objects.exists())

    def test_delete_blocked_by_usage(self):
        Unit.objects.create(name="BOX")
        with mock.patch.object(services, "tables_using", return_value=["item", "part-mst"]):
            response = self.client.post(reverse("units:api_delete", args=["BOX"]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("item, part-mst", response.json()["message"])
        self.assertTrue(Unit.objects.exists())

    def test_writes_can_be_switched_off(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            response = self.client.post(reverse("units:api_create"), {"name": "BOX"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Unit.objects.exists())

    def test_login_required(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("units:master")).status_code, 200)

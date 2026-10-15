from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import Material


class MaterialMasterTests(TestCase):
    """mat_mst is the old software's table (unmanaged), so tests create it themselves."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Material)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(Material)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="operator", password="S3cure-pass!")

    def setUp(self):
        Material.objects.create(code="A001", name="ALUMINIUM")
        Material.objects.create(code="B001", name="BRASS")
        self.client.force_login(self.user)

    def post(self, url=None, **data):
        base = {"name": "  aluminium  sheet "}
        base.update(data)
        return self.client.post(url or reverse("materials:api_create"), base)

    def test_grid_loads_records(self):
        response = self.client.get(reverse("materials:master"))
        self.assertContains(response, "Material Master")
        materials = self.client.get(reverse("materials:api_list")).json()["materials"]
        self.assertEqual([(m["code"], m["name"]) for m in materials],
                         [("A001", "ALUMINIUM"), ("B001", "BRASS")])

    def test_add_generates_code_from_first_letter(self):
        self.assertEqual(self.client.get(reverse("materials:api_next_code"), {"name": "Aluminium Sheet"}).json()["code"], "A002")
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Material.objects.filter(code="A002", name="ALUMINIUM SHEET").exists())

    def test_add_new_letter_starts_at_001(self):
        response = self.post(name="Copper")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Material.objects.filter(code="C001").exists())

    def test_add_numeric_first_char_code(self):
        response = self.post(name="86/20")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Material.objects.filter(code="8001").exists())

    def test_validation(self):
        response = self.post(name="   ")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json()["errors"])

    def test_duplicate_name_rejected(self):
        self.assertEqual(self.post(name="aluminium").status_code, 409)

    def test_modify_keeps_code(self):
        response = self.post(url=reverse("materials:api_update", args=["A001"]), name="Aluminium Alloy")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Material.objects.get(code="A001").name, "ALUMINIUM ALLOY")
        self.assertEqual(Material.objects.count(), 2)

    def test_delete(self):
        self.assertEqual(self.client.post(reverse("materials:api_delete", args=["A001"])).status_code, 200)
        self.assertFalse(Material.objects.filter(code="A001").exists())

    def test_delete_blocked_when_used(self):
        with mock.patch.object(services, "USAGE_TABLES", [("apc", "material")]), \
             mock.patch.object(services, "values_in_use", return_value={"A001"}):
            response = self.client.post(reverse("materials:api_delete", args=["A001"]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("cannot be deleted", response.json()["message"])
        self.assertTrue(Material.objects.filter(code="A001").exists())

    def test_login_and_post_only(self):
        self.assertEqual(self.client.get(reverse("materials:api_delete", args=["A001"])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("materials:master")).status_code, 302)

    def test_writes_switch(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            self.assertEqual(self.post().status_code, 403)

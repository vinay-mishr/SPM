from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import MarketingManager


class MarketingManagerTests(TestCase):
    """mm_mst is the old software's table (unmanaged), so tests create it themselves."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(MarketingManager)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(MarketingManager)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="operator", password="S3cure-pass!")

    def setUp(self):
        MarketingManager.objects.create(code="01", name="PUSHPINDER")
        MarketingManager.objects.create(code="02", name="N/A")
        self.client.force_login(self.user)

    def post(self, url=None, **data):
        base = {"name": " rahul  sharma ", "address_1": "SCO 12", "address_2": "Phase 8",
                "city": "mohali", "mobile": "+91 98765 43210"}
        base.update(data)
        return self.client.post(url or reverse("marketing:api_create"), base)

    def test_grid_loads_records(self):
        response = self.client.get(reverse("marketing:master"))
        self.assertContains(response, "Manager Name")
        self.assertEqual(self.client.get(reverse("marketing:api_list")).json()["managers"][0]["name"], "N/A")

    def test_add_generates_next_code_and_cleans(self):
        self.assertEqual(self.client.get(reverse("marketing:api_next_code")).json()["code"], "03")
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        m = MarketingManager.objects.get(code="03")
        # City is no longer part of the Add/Modify form (kept in the database/grid only).
        self.assertEqual((m.name, m.city, m.mobile, m.address_1), ("RAHUL SHARMA", None, "9876543210", "SCO 12"))

    def test_validation(self):
        response = self.post(name="  ", mobile="12345")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"name", "mobile"})

    def test_duplicate_name_rejected(self):
        self.assertEqual(self.post(name="pushpinder").status_code, 409)

    def test_modify_keeps_code(self):
        response = self.post(url=reverse("marketing:api_update", args=["01"]), name="Pushpinder Singh", mobile="")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(MarketingManager.objects.get(code="01").name, "PUSHPINDER SINGH")
        self.assertEqual(MarketingManager.objects.count(), 2)

    def test_delete_blocked_when_used(self):
        with mock.patch.object(services, "tables_using", return_value=["cust_mst"]):
            response = self.client.post(reverse("marketing:api_delete", args=["01"]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("cust_mst", response.json()["message"])
        self.assertTrue(MarketingManager.objects.filter(code="01").exists())

    def test_delete(self):
        self.assertEqual(self.client.post(reverse("marketing:api_delete", args=["02"])).status_code, 200)
        self.assertFalse(MarketingManager.objects.filter(code="02").exists())

    def test_login_and_post_only(self):
        self.assertEqual(self.client.get(reverse("marketing:api_delete", args=["02"])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("marketing:master")).status_code, 302)

    def test_writes_switch(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            self.assertEqual(self.post().status_code, 403)

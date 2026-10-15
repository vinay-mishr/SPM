from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import Rep


class RepMasterTests(TestCase):
    """rep_mst is the old software's table (unmanaged), so tests create it themselves."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Rep)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(Rep)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="operator", password="S3cure-pass!")

    def setUp(self):
        Rep.objects.create(code="02", name="PUSHPINDER", mobile="9216901409")
        Rep.objects.create(code="03", name="N/A")
        self.client.force_login(self.user)

    def post(self, url=None, **data):
        base = {"name": " kiran  kumar ", "father_name": "ram lal", "address_1": "H.No. 12", "address_2": "Phase 3",
                "address_3": "Mohali", "permanent_location": "Kharar", "mobile": "098765 43210"}
        base.update(data)
        return self.client.post(url or reverse("reps:api_create"), base)

    def test_grid_loads_records(self):
        self.assertContains(self.client.get(reverse("reps:master")), "Rep Name")
        reps = self.client.get(reverse("reps:api_list")).json()["reps"]
        self.assertEqual([(r["code"], r["name"]) for r in reps], [("03", "N/A"), ("02", "PUSHPINDER")])

    def test_add_saves_all_fields_with_next_code(self):
        self.assertEqual(self.client.get(reverse("reps:api_next_code")).json()["code"], "04")
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        r = Rep.objects.get(code="04")
        self.assertEqual(
            (r.name, r.father_name, r.address_1, r.address_2, r.address_3, r.permanent_location, r.mobile),
            ("KIRAN KUMAR", "RAM LAL", "H.No. 12", "Phase 3", "Mohali", "Kharar", "9876543210"),
        )

    def test_next_code_skips_codes_used_in_old_bills(self):
        with mock.patch.object(services, "values_in_use", return_value={"04", "18"}):
            self.assertEqual(services.next_code(), "19")

    def test_validation(self):
        response = self.post(name=" ", mobile="98765")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"name", "mobile"})

    def test_duplicate_name_rejected(self):
        self.assertEqual(self.post(name="Pushpinder").status_code, 409)

    def test_modify_keeps_code(self):
        response = self.post(url=reverse("reps:api_update", args=["02"]), name="Pushpinder", mobile="9216901409")
        self.assertEqual(response.status_code, 200, response.content)
        r = Rep.objects.get(code="02")
        self.assertEqual((r.father_name, r.permanent_location), ("RAM LAL", "Kharar"))
        self.assertEqual(Rep.objects.count(), 2)

    def test_delete_blocked_when_used(self):
        with mock.patch.object(services, "tables_using", return_value=["cust_mst", "bill"]):
            response = self.client.post(reverse("reps:api_delete", args=["03"]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("already being used", response.json()["message"])
        self.assertTrue(Rep.objects.filter(code="03").exists())

    def test_delete(self):
        self.assertEqual(self.client.post(reverse("reps:api_delete", args=["03"])).status_code, 200)
        self.assertFalse(Rep.objects.filter(code="03").exists())

    def test_login_and_post_only(self):
        self.assertEqual(self.client.get(reverse("reps:api_delete", args=["03"])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("reps:master")).status_code, 302)

    def test_writes_switch(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            self.assertEqual(self.post().status_code, 403)

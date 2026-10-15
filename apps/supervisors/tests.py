from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import Supervisor


class SupervisorMasterTests(TestCase):
    """sup_mst is the old software's table (unmanaged), so tests create it themselves."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Supervisor)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(Supervisor)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="operator", password="S3cure-pass!")

    def setUp(self):
        Supervisor.objects.create(code="R001", name="RANDHIR SINGH")
        Supervisor.objects.create(code="G001", name="GANESH NAYEK")
        self.client.force_login(self.user)

    def post(self, url=None, **data):
        base = {"name": "  ganesh  kumar "}
        base.update(data)
        return self.client.post(url or reverse("supervisors:api_create"), base)

    def test_grid_loads_records(self):
        response = self.client.get(reverse("supervisors:master"))
        self.assertContains(response, "Supervisor Master")
        supervisors = self.client.get(reverse("supervisors:api_list")).json()["supervisors"]
        self.assertEqual([(s["code"], s["name"]) for s in supervisors],
                         [("G001", "GANESH NAYEK"), ("R001", "RANDHIR SINGH")])

    def test_add_generates_code_from_first_letter(self):
        self.assertEqual(self.client.get(reverse("supervisors:api_next_code"), {"name": "Ganesh Kumar"}).json()["code"], "G002")
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Supervisor.objects.filter(code="G002", name="GANESH KUMAR").exists())

    def test_add_new_letter_starts_at_001(self):
        response = self.post(name="Sanjay Mehta")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Supervisor.objects.filter(code="S001").exists())

    def test_validation(self):
        response = self.post(name="   ")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json()["errors"])

    def test_duplicate_name_rejected(self):
        self.assertEqual(self.post(name="ganesh nayek").status_code, 409)

    def test_modify_keeps_code(self):
        response = self.post(url=reverse("supervisors:api_update", args=["G001"]), name="Ganesh Nayek Jr")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Supervisor.objects.get(code="G001").name, "GANESH NAYEK JR")
        self.assertEqual(Supervisor.objects.count(), 2)

    def test_delete(self):
        self.assertEqual(self.client.post(reverse("supervisors:api_delete", args=["G001"])).status_code, 200)
        self.assertFalse(Supervisor.objects.filter(code="G001").exists())

    def test_delete_blocked_when_used(self):
        with mock.patch.object(services, "USAGE_TABLES", [("cust_mst", "crep")]), \
             mock.patch.object(services, "values_in_use", return_value={"G001"}):
            response = self.client.post(reverse("supervisors:api_delete", args=["G001"]))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Supervisor.objects.filter(code="G001").exists())

    def test_login_and_post_only(self):
        self.assertEqual(self.client.get(reverse("supervisors:api_delete", args=["G001"])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("supervisors:master")).status_code, 302)

    def test_writes_switch(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            self.assertEqual(self.post().status_code, 403)

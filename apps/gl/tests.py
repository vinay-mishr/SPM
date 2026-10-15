from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import Ledger


class GledMstTableMixin:
    """gled_mst and grp_mst are the old software's tables (unmanaged); tests create them."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Ledger)
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE grp_mst (gr_code decimal(5,0), gr_name varchar(30), gr_type varchar(1))")
            cursor.execute("INSERT INTO grp_mst VALUES (22, 'Sale', 'C')")
            cursor.execute("INSERT INTO grp_mst VALUES (23, 'Purchase', 'D')")
            cursor.execute("INSERT INTO grp_mst VALUES (5, 'Cash', 'D')")
            cursor.execute("CREATE TABLE group1 (grp_code varchar(10), grp_name varchar(100))")
            cursor.execute("INSERT INTO group1 VALUES ('A', 'LIABILITY')")
            cursor.execute("INSERT INTO group1 VALUES ('A01', 'SHARE HOLDERS FUNDS')")
            cursor.execute("INSERT INTO group1 VALUES ('B0302', 'SUNDRY DEBTORS')")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE grp_mst")
            cursor.execute("DROP TABLE group1")
        with connection.schema_editor() as editor:
            editor.delete_model(Ledger)


class GeneralLedgerTests(GledMstTableMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="operator", password="S3cure-pass!")
        cls.user.user_permissions.add(Permission.objects.get(codename="change_general_ledger"))

    def setUp(self):
        self.client.force_login(self.user)

    def post_ledger(self, url=None, **overrides):
        data = {"description": "  Advance  ", "group_code": "22", "opening_balance": "1500.50"}
        data.update(overrides)
        return self.client.post(url or reverse("gl:api_create"), data)

    def test_grid_shows_reference_columns(self):
        response = self.client.get(reverse("gl:master"))
        for heading in ("Description", "Group", "Opening Balance", "Code"):
            self.assertContains(response, heading)

    def test_create_maps_to_gled_mst_columns(self):
        response = self.post_ledger()
        self.assertEqual(response.status_code, 200, response.content)
        ledger = Ledger.objects.get()
        self.assertEqual(ledger.ledger_code, "A001")  # first letter of the description + 001
        self.assertEqual(ledger.description, "ADVANCE")
        self.assertEqual(ledger.group_code, Decimal("22"))
        self.assertEqual(ledger.group_name, "Sale")
        self.assertEqual(ledger.opening_balance, Decimal("1500.50"))

    def test_codes_follow_first_letter(self):
        self.post_ledger()
        self.post_ledger(description="Advance Two")
        self.post_ledger(description="Bank Charges", group_code="23")
        self.assertEqual(
            sorted(Ledger.objects.values_list("ledger_code", flat=True)), ["A001", "A002", "B001"]
        )

    def test_validation_messages(self):
        response = self.post_ledger(description=" ", group_code="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"description", "group_code"})
        self.assertFalse(Ledger.objects.exists())

    def test_unknown_group_rejected(self):
        response = self.post_ledger(group_code="999")
        self.assertEqual(response.status_code, 400)
        self.assertIn("group_code", response.json()["errors"])

    def test_default_opening_balance_is_zero(self):
        response = self.post_ledger(opening_balance="")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Ledger.objects.get().opening_balance, Decimal("0.00"))

    def test_modify_keeps_code_and_updates_fields(self):
        self.post_ledger()
        response = self.client.post(reverse("gl:api_update", args=["A001"]), {
            "description": "Advance Payment", "group_code": "23", "opening_balance": "200",
        })
        self.assertEqual(response.status_code, 200, response.content)
        ledger = Ledger.objects.get(ledger_code="A001")
        self.assertEqual((ledger.description, ledger.group_name, Ledger.objects.count()), ("ADVANCE PAYMENT", "Purchase", 1))

    def test_delete_blocked_by_usage(self):
        self.post_ledger()
        with mock.patch.object(services, "tables_using", return_value=["trial", "pur_mst"]):
            response = self.client.post(reverse("gl:api_delete", args=["A001"]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("trial, pur_mst", response.json()["message"])
        self.assertTrue(Ledger.objects.exists())

    def test_delete(self):
        self.post_ledger()
        self.assertEqual(self.client.post(reverse("gl:api_delete", args=["A001"])).status_code, 200)
        self.assertFalse(Ledger.objects.exists())

    def test_next_code_preview(self):
        self.post_ledger()
        response = self.client.get(reverse("gl:api_next_code"), {"description": "Advance Two"})
        self.assertEqual(response.json()["code"], "A002")

    def test_writes_can_be_switched_off(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            self.assertEqual(self.post_ledger().status_code, 403)
        self.assertFalse(Ledger.objects.exists())

    def test_login_required(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("gl:master")).status_code, 200)


class LedgerOpeningBalanceTests(GledMstTableMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_user(username="ob_editor", password="S3cure-pass!")
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_ledger_opening_balance"))
        cls.viewer = get_user_model().objects.create_user(username="ob_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.editor)
        Ledger.objects.create(ledger_code="A001", description="ADVANCE", opening_balance=Decimal("500.00"))
        Ledger.objects.create(ledger_code="B001", description="BANK CHARGES", opening_balance=Decimal("-120.00"))
        Ledger.objects.create(ledger_code="C001", description="CASH IN HAND", opening_balance=None)

    def test_page_renders(self):
        response = self.client.get(reverse("gl:opening_balance"))
        self.assertContains(response, "Main Ledger (Op. Balance)")

    def test_rows_split_positive_and_negative_balances(self):
        response = self.client.get(reverse("gl:opening_balance_data"))
        rows = {r["code"]: r for r in response.json()["rows"]}
        self.assertEqual((rows["A001"]["debit"], rows["A001"]["credit"]), ("500.00", "0.00"))
        self.assertEqual((rows["B001"]["debit"], rows["B001"]["credit"]), ("0.00", "120.00"))
        self.assertEqual((rows["C001"]["debit"], rows["C001"]["credit"]), ("0.00", "0.00"))

    def test_totals_and_difference(self):
        response = self.client.get(reverse("gl:opening_balance_data"))
        totals = response.json()["totals"]
        # Debit 500, Credit 120 -> Credit difference 380, both foot to 500.
        self.assertEqual(totals, {
            "debit": "500.00", "credit": "120.00",
            "diff_debit": "0.00", "diff_credit": "380.00",
            "grand_debit": "500.00", "grand_credit": "500.00",
        })

    def test_confirm_saves_signed_balance(self):
        response = self.client.post(
            reverse("gl:opening_balance_save"),
            data='{"changes": [{"code": "C001", "debit": "250.00", "credit": ""}]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Ledger.objects.get(ledger_code="C001").opening_balance, Decimal("250.00"))

    def test_credit_entry_saves_negative_balance(self):
        response = self.client.post(
            reverse("gl:opening_balance_save"),
            data='{"changes": [{"code": "A001", "debit": "", "credit": "75.00"}]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Ledger.objects.get(ledger_code="A001").opening_balance, Decimal("-75.00"))

    def test_both_debit_and_credit_rejected(self):
        response = self.client.post(
            reverse("gl:opening_balance_save"),
            data='{"changes": [{"code": "A001", "debit": "10.00", "credit": "5.00"}]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("A001", response.json()["errors"])

    def test_viewer_cannot_save(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("gl:opening_balance_save"),
            data='{"changes": [{"code": "A001", "debit": "10.00", "credit": ""}]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

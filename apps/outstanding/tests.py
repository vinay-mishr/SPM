from decimal import Decimal
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.parties.models import Party

from . import services
from .models import Bill


class PreviousOutstandingTests(TestCase):
    """bill and cust_mst are the old software's tables (unmanaged): tests create them."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Party)
        with connection.cursor() as cursor:
            # Like the real bill table: no primary key / unique constraint (invoice numbers repeat).
            cursor.execute(
                "CREATE TABLE bill (bill_no varchar(5), div varchar(2), b_date date, p_code varchar(4), "
                "n_amount decimal(10,2), amount decimal(10,2), c_dis decimal(10,2), amt_rcd decimal(10,2), "
                "pmt_rcd varchar(1))"
            )
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE bill")
        with connection.schema_editor() as editor:
            editor.delete_model(Party)

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.editor = User.objects.create_user(username="accounts", password="S3cure-pass!")
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_previous_outstanding"))
        cls.viewer = User.objects.create_user(username="viewer", password="S3cure-pass!")

    def setUp(self):
        Party.objects.create(party_code="A034", name="A&I ENGINEERS")
        Party.objects.create(party_code="S014", name="SUPER SOAPS")
        self.client.force_login(self.editor)

    def post_bill(self, key="", **overrides):
        data = {"div": "ol", "bill_no": "66", "bill_date": "2026-03-28", "party_code": "A034",
                "net_amount": "3245", "cash_discount": "", "key": key}
        data.update(overrides)
        return self.client.post(reverse("outstanding:api_save"), data)

    def test_grid_page_first(self):
        Bill.objects.create(bill_no="12", div="OL", bill_date=date(2026, 1, 5), party_code="A034",
                            net_amount=Decimal("500"), cash_discount=Decimal("0"))
        response = self.client.get(reverse("outstanding:master"))
        self.assertContains(response, "Invoice Date")
        bills = response.context["initial_data"]["bills"]
        self.assertEqual([(b["bill_no"], b["party_name"]) for b in bills], [("12", "A&I ENGINEERS")])
        self.assertNotContains(response, "View only")

    def test_add_maps_to_bill_columns(self):
        response = self.post_bill()
        self.assertEqual(response.status_code, 200, response.content)
        bill = Bill.objects.get()
        self.assertEqual((bill.div, bill.bill_no, bill.party_code), ("OL", "66", "A034"))
        self.assertEqual(bill.bill_date, date(2026, 3, 28))
        self.assertEqual((bill.net_amount, bill.amount, bill.cash_discount),
                         (Decimal("3245"), Decimal("3245"), Decimal("0")))

    def test_validation(self):
        response = self.post_bill(div="", bill_no="", bill_date="31-02-2026", party_code="ZZZZ", net_amount="0")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"div", "bill_no", "bill_date", "party_code", "net_amount"})
        self.assertEqual(self.post_bill(net_amount="12a").status_code, 400)
        self.assertEqual(self.post_bill(net_amount="1.234").status_code, 400)
        self.assertEqual(self.post_bill(cash_discount="-5").status_code, 400)
        self.assertFalse(Bill.objects.exists())

    def test_date_accepts_dd_mm_yyyy(self):
        self.assertEqual(self.post_bill(bill_date="05-04-2026").status_code, 200)
        self.assertEqual(Bill.objects.get().bill_date, date(2026, 4, 5))

    def test_duplicate_invoice_rejected(self):
        self.post_bill()
        response = self.post_bill()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Bill.objects.count(), 1)

    def test_modify_same_row(self):
        self.post_bill()
        response = self.post_bill(key="OL|66|A034", net_amount="3000.50", cash_discount="50", party_code="S014")
        self.assertEqual(response.status_code, 200, response.content)
        bill = Bill.objects.get()
        self.assertEqual((bill.party_code, bill.net_amount, bill.cash_discount),
                         ("S014", Decimal("3000.50"), Decimal("50")))

    def test_modify_and_delete_refused_when_receipt_exists(self):
        self.post_bill()
        Bill.objects.filter(bill_no="66").update(amount_received=Decimal("100"))
        self.assertEqual(self.post_bill(key="OL|66|A034", net_amount="1").status_code, 409)
        response = self.client.post(reverse("outstanding:api_delete"), {"key": "OL|66|A034"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("receipt", response.json()["message"])
        self.assertTrue(Bill.objects.exists())

    def test_delete(self):
        self.post_bill()
        response = self.client.post(reverse("outstanding:api_delete"), {"key": "OL|66|A034"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Bill.objects.exists())

    def test_duplicate_rows_are_not_changed(self):
        for _ in range(2):
            Bill.objects.create(bill_no="7", div="OL", party_code="A034", net_amount=Decimal("1"))
        response = self.client.post(reverse("outstanding:api_delete"), {"key": "OL|7|A034"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Bill.objects.filter(bill_no="7").count(), 2)

    def test_party_search(self):
        response = self.client.get(reverse("outstanding:api_parties"), {"q": "soap"})
        self.assertEqual(response.json()["parties"], [{"code": "S014", "name": "SUPER SOAPS", "city": ""}])

    def test_permission_and_login(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.post_bill().status_code, 403)
        self.assertContains(self.client.get(reverse("outstanding:master")), "View only")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("outstanding:master")).status_code, 302)
        self.assertFalse(Bill.objects.exists())

    def test_writes_switch(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            self.assertEqual(self.post_bill().status_code, 403)

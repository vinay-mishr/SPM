from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.outstanding.models import Bill
from apps.parties.models import Party

from . import payment, services
from .models import CreditorBill, PaymentDetail


class CreditorOutstandingTests(TestCase):
    """bill and cust_mst are the old software's tables (unmanaged): tests create them."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Party)
        with connection.cursor() as cursor:
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
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_creditor_outstanding"))
        cls.viewer = User.objects.create_user(username="viewer", password="S3cure-pass!")

    def setUp(self):
        Party.objects.create(party_code="A001", name="A.S.ENGINEERS", group_code="S002")  # vendor
        Party.objects.create(party_code="B001", name="BETA SUPPLIES", group_code="S002")  # vendor
        Party.objects.create(party_code="S014", name="SUPER SOAPS", group_code="S001")  # customer, NOT a vendor
        self.client.force_login(self.editor)

    def post_bill(self, key="", **overrides):
        data = {"div": "ol", "bill_no": "66", "bill_date": "2026-03-28", "party_code": "A001",
                "net_amount": "3245", "cash_discount": "", "key": key}
        data.update(overrides)
        return self.client.post(reverse("creditor_outstanding:api_save"), data)

    def test_grid_page_first(self):
        Bill.objects.create(bill_no="12", div="OL", bill_date=date(2026, 1, 5), party_code="A001",
                            net_amount=Decimal("500"), cash_discount=Decimal("0"))
        response = self.client.get(reverse("creditor_outstanding:master"))
        self.assertContains(response, "Invoice Date")
        bills = response.context["initial_data"]["bills"]
        self.assertEqual([(b["bill_no"], b["party_name"]) for b in bills], [("12", "A.S.ENGINEERS")])
        self.assertNotContains(response, "View only")

    def test_only_creditor_bills_are_shown(self):
        """A customer (S001) bill must never appear on this screen, even though it's the same table."""
        Bill.objects.create(bill_no="1", div="OL", party_code="A001", net_amount=Decimal("100"))  # vendor
        Bill.objects.create(bill_no="2", div="OL", party_code="S014", net_amount=Decimal("200"))  # customer
        rows = services.list_bills("OL")
        self.assertEqual([r["bill_no"] for r in rows], ["1"])

    def test_add_maps_to_bill_columns(self):
        response = self.post_bill()
        self.assertEqual(response.status_code, 200, response.content)
        bill = Bill.objects.get()
        self.assertEqual((bill.div, bill.bill_no, bill.party_code), ("OL", "66", "A001"))
        self.assertEqual(bill.bill_date, date(2026, 3, 28))
        self.assertEqual((bill.net_amount, bill.amount, bill.cash_discount),
                         (Decimal("3245"), Decimal("3245"), Decimal("0")))

    def test_customer_party_is_rejected(self):
        """This screen is creditor-only: a debtor party code must be refused."""
        response = self.post_bill(party_code="S014")
        self.assertEqual(response.status_code, 400)
        self.assertIn("party_code", response.json()["errors"])
        self.assertFalse(Bill.objects.exists())

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
        response = self.post_bill(key="OL|66|A001", net_amount="3000.50", cash_discount="50", party_code="B001")
        self.assertEqual(response.status_code, 200, response.content)
        bill = Bill.objects.get()
        self.assertEqual((bill.party_code, bill.net_amount, bill.cash_discount),
                         ("B001", Decimal("3000.50"), Decimal("50")))

    def test_modify_and_delete_refused_when_receipt_exists(self):
        self.post_bill()
        Bill.objects.filter(bill_no="66").update(amount_received=Decimal("100"))
        self.assertEqual(self.post_bill(key="OL|66|A001", net_amount="1").status_code, 409)
        response = self.client.post(reverse("creditor_outstanding:api_delete"), {"key": "OL|66|A001"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("receipt", response.json()["message"])
        self.assertTrue(Bill.objects.exists())

    def test_delete(self):
        self.post_bill()
        response = self.client.post(reverse("creditor_outstanding:api_delete"), {"key": "OL|66|A001"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Bill.objects.exists())

    def test_duplicate_rows_are_not_changed(self):
        for _ in range(2):
            Bill.objects.create(bill_no="7", div="OL", party_code="A001", net_amount=Decimal("1"))
        response = self.client.post(reverse("creditor_outstanding:api_delete"), {"key": "OL|7|A001"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Bill.objects.filter(bill_no="7").count(), 2)

    def test_vendor_search_excludes_customers(self):
        response = self.client.get(reverse("creditor_outstanding:api_vendors"), {"q": "a"})
        codes = [p["code"] for p in response.json()["parties"]]
        self.assertIn("A001", codes)
        self.assertNotIn("S014", codes)

    def test_permission_and_login(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("creditor_outstanding:master")).status_code, 200)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("creditor_outstanding:master"))
        self.assertContains(response, "View only")
        self.assertEqual(self.post_bill().status_code, 403)


class PaymentBillBalanceTests(TestCase):
    """cr_out, p_col, trans and vno are the old software's tables (unmanaged): tests create them."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Party)
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE cr_out (id INTEGER PRIMARY KEY AUTOINCREMENT, div varchar(2), inv_no varchar(10), "
                "inv_dt date, p_code varchar(4), amount decimal(10,2), dr_amt decimal(10,2), tds_amt decimal(10,2), "
                "pmt_rcd decimal(10,2), c_dis decimal(10,2), int_amt decimal(10,2), pmt_mad varchar(1), "
                "nar varchar(20), mrn_no varchar(10), cl_date date, uname varchar(10))")
            cursor.execute(
                "CREATE TABLE p_col (id INTEGER PRIMARY KEY AUTOINCREMENT, div varchar(2), bill_no varchar(10), "
                "b_date date, b_amt decimal(10,2), p_code varchar(4), amount decimal(10,2), c_dis decimal(10,2), "
                "int_amt decimal(10,2), nar varchar(20), date date, remk varchar(40), uname varchar(10))")
            cursor.execute(
                "CREATE TABLE trans (id INTEGER PRIMARY KEY AUTOINCREMENT, ttype varchar(2), tdoc decimal(10,0), "
                "tdate date, tcode varchar(6), tccode varchar(6), tdbcr varchar(1), tnar1 varchar(40), "
                "tnar2 varchar(40), tamt decimal(12,2), nar varchar(20), p_code varchar(4), div varchar(2), "
                "uname varchar(10))")
            cursor.execute(
                "CREATE TABLE vno (id INTEGER PRIMARY KEY AUTOINCREMENT, date date, cvvno decimal(10,0), "
                "jvvno decimal(10,0))")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.cursor() as cursor:
            for table in ("cr_out", "p_col", "trans", "vno"):
                cursor.execute(f"DROP TABLE {table}")
        with connection.schema_editor() as editor:
            editor.delete_model(Party)

    def setUp(self):
        from unittest import mock
        from django.db import transaction as dj_transaction

        patcher = mock.patch.object(payment, "transaction", mock.Mock(atomic=lambda using=None: dj_transaction.atomic()))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(payment, "connections", {"legacy": connection})
        patcher.start()
        self.addCleanup(patcher.stop)
        Party.objects.create(party_code="A049", name="A.S.ENGINEERS", group_code="S002")
        Party.objects.create(party_code="B001", name="BETA SUPPLIES", group_code="S002")
        CreditorBill.objects.bulk_create([
            CreditorBill(div="OL", inv_no="792", inv_dt=date(2024, 10, 22), p_code="A049",
                         amount=Decimal("49112.00"), dr_amt=Decimal("0"), tds_amt=Decimal("0"),
                         pmt_rcd=Decimal("0"), c_dis=Decimal("0"), int_amt=Decimal("0"), pmt_mad="N"),
            CreditorBill(div="OL", inv_no="806", inv_dt=date(2024, 11, 28), p_code="A049",
                         amount=Decimal("65284.00"), dr_amt=Decimal("0"), tds_amt=Decimal("0"),
                         pmt_rcd=Decimal("0"), c_dis=Decimal("0"), int_amt=Decimal("0"), pmt_mad="N"),
            CreditorBill(div="OL", inv_no="90", inv_dt=date(2024, 1, 1), p_code="B001",
                         amount=Decimal("1000.00"), dr_amt=Decimal("0"), tds_amt=Decimal("0"),
                         pmt_rcd=Decimal("0"), c_dis=Decimal("0"), int_amt=Decimal("0"), pmt_mad="N"),
        ])

    def pay(self, bill_no, amount, chq_no, party="A049"):
        dates = {"792": "2024-10-22", "806": "2024-11-28"}
        line = {"div": "OL", "bill_no": bill_no, "bill_date": dates[bill_no], "bill_amount": "0",
                "balance": "0", "cash_dis": "0", "interest": "0", "adjusted": str(amount)}
        return payment.save_payment({"party_code": party, "chq_no": chq_no, "mode": "CA", "date": "2026-10-06",
                                     "amount_paid": str(amount), "bank_charges": "0", "lines": [line]},
                                    username="accounts")

    def balances(self, party="A049"):
        return {r["bill_no"]: r["balance"] for r in payment.pending_bills(party)}

    def test_balance_accumulates_and_paid_bill_leaves_list(self):
        self.pay("792", "9112.00", "P1")
        self.assertEqual(self.balances()["792"], "40000.00")
        self.pay("792", "10000.00", "P2")
        self.assertEqual(self.balances()["792"], "30000.00")
        self.assertEqual(payment.pending_bills("A049")[0]["bill_amount"], "49112.00")
        self.pay("792", "30000.00", "P3")
        self.assertNotIn("792", self.balances())
        self.assertEqual(CreditorBill.objects.get(inv_no="792").amount, Decimal("49112.00"))

    def test_overpayment_refused_and_nothing_saved(self):
        self.pay("792", "49112.00", "P1")
        with self.assertRaises(payment.PaymentError):
            self.pay("792", "1.00", "P2")
        self.assertEqual(PaymentDetail.objects.filter(nar="P2").count(), 0)

    def test_other_bills_and_vendors_are_not_affected(self):
        self.pay("792", "9112.00", "P1")
        self.assertEqual(self.balances()["806"], "65284.00")
        self.pay("806", "5000.00", "P2")
        self.assertEqual(self.balances()["792"], "40000.00")
        self.assertEqual(self.balances("B001")["90"], "1000.00")

    def test_same_bill_number_different_dates_are_separate_bills(self):
        CreditorBill.objects.create(div="OL", inv_no="260", inv_dt=date(2021, 8, 10), p_code="A049",
                                    amount=Decimal("47696.00"), dr_amt=Decimal("0"), tds_amt=Decimal("0"),
                                    pmt_rcd=Decimal("0"), c_dis=Decimal("0"), int_amt=Decimal("0"), pmt_mad="N")
        CreditorBill.objects.create(div="OL", inv_no="260", inv_dt=date(2021, 9, 17), p_code="A049",
                                    amount=Decimal("29117.00"), dr_amt=Decimal("0"), tds_amt=Decimal("0"),
                                    pmt_rcd=Decimal("0"), c_dis=Decimal("0"), int_amt=Decimal("0"), pmt_mad="N")
        line = {"div": "OL", "bill_no": "260", "bill_date": "2021-09-17", "bill_amount": "29117",
                "balance": "29117", "cash_dis": "0", "interest": "0", "adjusted": "1421.00"}
        payment.save_payment({"party_code": "A049", "chq_no": "P9", "mode": "CA", "date": "2026-10-06",
                              "amount_paid": "1421.00", "bank_charges": "0", "lines": [line]}, username="accounts")
        first = CreditorBill.objects.get(inv_no="260", inv_dt=date(2021, 8, 10))
        second = CreditorBill.objects.get(inv_no="260", inv_dt=date(2021, 9, 17))
        self.assertEqual(first.pmt_rcd, Decimal("0"))
        self.assertEqual(second.pmt_rcd, Decimal("1421.00"))
        pending = {(r["bill_no"], r["bill_date"]): r["balance"] for r in payment.pending_bills("A049")}
        self.assertEqual(pending[("260", "2021-09-17")], "27696.00")
        self.assertEqual(pending[("260", "2021-08-10")], "47696.00")

    def test_delete_restores_balance(self):
        self.pay("792", "9112.00", "P1")
        self.pay("792", "10000.00", "P2")
        payment.delete_payment("A049", "P2")
        self.assertEqual(self.balances()["792"], "40000.00")

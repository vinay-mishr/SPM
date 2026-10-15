import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.parties.models import Party
from apps.parts.models import Part

from . import services
from .models import (
    CreditorOut, ItemMasterTransaction, MrnData, PartRateHistory, PurchaseOrderHeader, PurchaseOrderItem,
)


class PurchaseOrderTablesMixin:
    """pord_mst, order and rt_mst are the old software's tables (unmanaged); tests create them,
    alongside cust_mst (Party) and part-mst (Part) which a PO always references."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Party)
            editor.create_model(Part)
            editor.create_model(PurchaseOrderHeader)
            editor.create_model(PurchaseOrderItem)
            editor.create_model(PartRateHistory)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(PartRateHistory)
            editor.delete_model(PurchaseOrderItem)
            editor.delete_model(PurchaseOrderHeader)
            editor.delete_model(Part)
            editor.delete_model(Party)


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class PurchaseOrderMasterTests(PurchaseOrderTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_user(username="po_editor", password="S3cure-pass!")
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_purchase_order"))
        cls.viewer = get_user_model().objects.create_user(username="po_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.editor)
        self.vendor = Party.objects.create(
            party_code="A009", group_code="S002", name="ASSOCIATE BELTING",
            city="Mohali", state_gst_code="03",
        )
        self.part = Part.objects.create(
            part_number="BT01_015", description_1="FLAT", material="RUBBER", unit="NUM",
            hsn_code="5910", gst_percent=Decimal("18.00"), purchase_rate=Decimal("155.0000"),
            packing=10, current_stock=Decimal("25.000"), gauge="10MM",
        )

    def post_order(self, **overrides):
        data = {
            "div": "SP",
            "party_code": "A009",
            "order_date": "2026-09-10",
            "remarks": "",
            "lines": [
                {"part_code": "BT01_015", "po_qty": "10", "quantity": "10", "unit": "NUM",
                 "hsn_code": "5910", "rate": "155.0000", "size": "10MM", "gst_percent": "18.00"},
            ],
            "key": "",
        }
        data.update(overrides)
        return self.client.post(
            reverse("purchase_orders:api_save"), data=json.dumps(data), content_type="application/json",
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:master"))
        self.assertContains(response, "Purchase Order Master")

    def test_create_saves_header_and_lines(self):
        response = self.post_order()
        self.assertEqual(response.status_code, 200, response.content)
        header = PurchaseOrderHeader.objects.get()
        self.assertEqual(header.div, "SP")
        self.assertEqual(header.po_no, "1")
        self.assertEqual(header.party_code, "A009")
        self.assertEqual(header.amount, Decimal("1550.00"))
        self.assertEqual(header.gst_amount, Decimal("279.00"))
        self.assertEqual(header.net_amount, Decimal("1829.00"))
        line = PurchaseOrderItem.objects.get()
        self.assertEqual(line.part_code, "BT01_015")
        self.assertEqual(line.po_qty, Decimal("10.000"))
        self.assertEqual(line.rate, Decimal("155.0000"))
        # Within the company's own state (03): CGST + SGST, no IGST.
        self.assertEqual(line.cgst_rate, Decimal("9.00"))
        self.assertEqual(line.sgst_rate, Decimal("9.00"))
        self.assertEqual(line.igst_rate, Decimal("0.00"))

    def test_next_po_number_increments_per_division(self):
        self.post_order()
        response = self.post_order()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(PurchaseOrderHeader.objects.count(), 2)
        self.assertEqual(set(PurchaseOrderHeader.objects.values_list("po_no", flat=True)), {"1", "2"})

    def test_interstate_party_uses_igst(self):
        Party.objects.filter(party_code="A009").update(state_gst_code="06")  # Haryana, not 03
        response = self.post_order()
        self.assertEqual(response.status_code, 200, response.content)
        line = PurchaseOrderItem.objects.get()
        self.assertEqual(line.cgst_rate, Decimal("0.00"))
        self.assertEqual(line.sgst_rate, Decimal("0.00"))
        self.assertEqual(line.igst_rate, Decimal("18.00"))

    def test_list_and_detail(self):
        self.post_order()
        list_response = self.client.get(reverse("purchase_orders:api_list"))
        orders = list_response.json()["orders"]
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["party_name"], "ASSOCIATE BELTING")
        self.assertEqual(orders[0]["city"], "Mohali")

        detail_response = self.client.get(reverse("purchase_orders:api_detail", args=["SP", "1"]))
        detail = detail_response.json()
        self.assertEqual(detail["party_code"], "A009")
        self.assertEqual(len(detail["lines"]), 1)
        self.assertEqual(detail["lines"][0]["part_name"], "FLAT")

    def test_modify_replaces_lines(self):
        self.post_order()
        response = self.post_order(
            key="SP|1",
            lines=[
                {"part_code": "BT01_015", "po_qty": "5", "quantity": "5", "unit": "NUM",
                 "hsn_code": "5910", "rate": "155.0000", "size": "10MM", "gst_percent": "18.00"},
            ],
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(PurchaseOrderHeader.objects.count(), 1)
        self.assertEqual(PurchaseOrderItem.objects.count(), 1)
        line = PurchaseOrderItem.objects.get()
        self.assertEqual(line.po_qty, Decimal("5.000"))
        header = PurchaseOrderHeader.objects.get()
        self.assertEqual(header.amount, Decimal("775.00"))

    def test_delete_removes_header_and_lines(self):
        self.post_order()
        response = self.client.post(reverse("purchase_orders:api_delete"), {"key": "SP|1"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(PurchaseOrderHeader.objects.count(), 0)
        self.assertEqual(PurchaseOrderItem.objects.count(), 0)

    def test_unknown_part_is_rejected(self):
        response = self.post_order(lines=[
            {"part_code": "NOPE", "po_qty": "1", "quantity": "1", "unit": "NUM", "rate": "10"},
        ])
        self.assertEqual(response.status_code, 400)
        self.assertIn("row0", response.json()["errors"])

    def test_viewer_cannot_save(self):
        self.client.force_login(self.viewer)
        response = self.post_order()
        self.assertEqual(response.status_code, 403)

    def test_part_reference_uses_supplier_specific_rate(self):
        self.part.supplier_1 = "A009"
        self.part.rate_1 = Decimal("140.0000")
        self.part.save()
        response = self.client.get(reverse("purchase_orders:api_part_reference"), {"code": "BT01_015", "vendor": "A009"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rate"], "140.0000")

    def test_previous_info_reads_rate_history(self):
        PartRateHistory.objects.create(
            part_code="BT01_015", order_date="2026-01-05", party_code="A009",
            rate=Decimal("150.0000"), quantity=Decimal("4.000"),
        )
        response = self.client.get(reverse("purchase_orders:api_previous_info", args=["BT01_015"]))
        history = response.json()["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["rate"], "150.0000")
        self.assertEqual(history[0]["party_name"], "ASSOCIATE BELTING")


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class PendingOrderReportTests(PurchaseOrderTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="report_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.vendor = Party.objects.create(
            party_code="A009", group_code="S002", name="ASSOCIATE BELTING",
            city="Mohali", grade="A", state_gst_code="03",
        )
        self.other_vendor = Party.objects.create(
            party_code="B003", group_code="S002", name="B.H.MECHANICAL WORKS",
            city="Ludhiana", grade="B", state_gst_code="03",
        )
        self.part = Part.objects.create(part_number="BT01_015", description_1="FLAT")
        # Fully pending line: ordered 10, received 0. (quantity == stk_qty is the field the
        # VFP report actually balances against, not po_qty/stock -- see services.pending_orders.)
        PurchaseOrderItem.objects.create(
            div="SP", po_no="27", part_code="BT01_015", order_date="2026-09-10", party_code="A009",
            quantity=Decimal("10.000"), received_qty=Decimal("0.000"), rate=Decimal("155.0000"),
            despatch_date="2026-09-12", adjusted="",
        )
        # Fully received line: must NOT appear as pending.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="26", part_code="BT01_015", order_date="2026-08-13", party_code="B003",
            quantity=Decimal("5.000"), received_qty=Decimal("5.000"), rate=Decimal("100.0000"),
            despatch_date="2026-08-14", adjusted="",
        )
        # Ordered after the "as on" date: must not appear.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="28", part_code="BT01_015", order_date="2026-09-20", party_code="A009",
            quantity=Decimal("2.000"), received_qty=Decimal("0.000"), rate=Decimal("50.0000"),
            despatch_date="2026-09-22", adjusted="",
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:pending_report"))
        self.assertContains(response, "Party Wise Pending Purchase Order")

    def test_all_parties_pending_as_on_date(self):
        response = self.client.get(reverse("purchase_orders:pending_report_data"), {"as_on": "2026-09-15"})
        groups = response.json()["groups"]
        # Only the fully-pending line (PO 27) qualifies; the received line and the
        # later-dated line are excluded.
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["party_code"], "A009")
        self.assertEqual(len(groups[0]["lines"]), 1)
        line = groups[0]["lines"][0]
        self.assertEqual(line["pending_qty"], "10.000")
        self.assertEqual(line["value"], "1550.00")
        self.assertEqual(line["delay_days"], 3)  # 2026-09-15 - 2026-09-12

    def test_selective_party_filter(self):
        response = self.client.get(
            reverse("purchase_orders:pending_report_data"), {"as_on": "2026-09-15", "party_code": "B003"},
        )
        groups = response.json()["groups"]
        self.assertEqual(groups, [])  # B003's only line is fully received

    def test_partially_received_line_still_pending(self):
        PurchaseOrderItem.objects.filter(po_no="26").update(received_qty=Decimal("2.000"))
        response = self.client.get(reverse("purchase_orders:pending_report_data"), {"as_on": "2026-09-15"})
        groups = {g["party_code"]: g for g in response.json()["groups"]}
        self.assertIn("B003", groups)
        self.assertEqual(groups["B003"]["lines"][0]["pending_qty"], "3.000")

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:pending_report_export"), {"as_on": "2026-09-15"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class PendingDespatchReportTests(PurchaseOrderTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="despatch_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.vendor = Party.objects.create(
            party_code="A009", group_code="S002", name="ASSOCIATE BELTING", city="Mohali", state_gst_code="03",
        )
        self.other_vendor = Party.objects.create(
            party_code="B003", group_code="S002", name="B.H.MECHANICAL WORKS", city="Ludhiana", state_gst_code="03",
        )
        self.part = Part.objects.create(part_number="BT01_015", description_1="FLAT")
        # Despatch date inside the range, still pending (10 - 0 > 0).
        PurchaseOrderItem.objects.create(
            div="SP", po_no="27", part_code="BT01_015", order_date="2026-09-05", party_code="A009",
            quantity=Decimal("10.000"), received_qty=Decimal("0.000"), despatch_date="2026-09-12", adjusted="X",
        )
        # Despatch date OUTSIDE the range: must not appear.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="26", part_code="BT01_015", order_date="2026-08-01", party_code="A009",
            quantity=Decimal("4.000"), received_qty=Decimal("0.000"), despatch_date="2026-08-01", adjusted="",
        )
        # Fully received, inside range: must not appear.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="25", part_code="BT01_015", order_date="2026-09-01", party_code="B003",
            quantity=Decimal("5.000"), received_qty=Decimal("5.000"), despatch_date="2026-09-10", adjusted="",
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:pending_despatch_report"))
        self.assertContains(response, "Party Wise Pending P.O. Despatch Report")

    def test_despatch_date_range_and_adj_ignored(self):
        # adj='X' on the qualifying line proves this report does NOT filter on adj
        # (unlike the plain Pending P.O. report), matching the VFP scan condition.
        response = self.client.get(reverse("purchase_orders:pending_despatch_report_data"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30", "run_date": "2026-09-20",
        })
        groups = response.json()["groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["party_code"], "A009")
        line = groups[0]["lines"][0]
        self.assertEqual(line["pending_qty"], "10.000")
        self.assertEqual(line["delay_days"], 8)  # 2026-09-20 - 2026-09-12

    def test_selective_party_filter(self):
        response = self.client.get(reverse("purchase_orders:pending_despatch_report_data"), {
            "start_date": "2026-08-01", "end_date": "2026-09-30", "run_date": "2026-09-20", "party_code": "B003",
        })
        self.assertEqual(response.json()["groups"], [])  # B003's only line is fully received

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:pending_despatch_report_export"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30", "run_date": "2026-09-20",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class ItemWisePendingReportTests(PurchaseOrderTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="item_wise_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.vendor = Party.objects.create(
            party_code="A009", group_code="S002", name="ASSOCIATE BELTING", city="Mohali", state_gst_code="03",
        )
        self.part = Part.objects.create(part_number="BT01_015", description_1="FLAT")
        self.other_part = Part.objects.create(part_number="BT01_020", description_1="DRUM")
        # Pending, on/before run date.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="27", part_code="BT01_015", order_date="2026-09-10", party_code="A009",
            quantity=Decimal("10.000"), received_qty=Decimal("2.000"), despatch_date="2026-09-12",
        )
        # Fully received: must not appear.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="26", part_code="BT01_020", order_date="2026-09-01", party_code="A009",
            quantity=Decimal("5.000"), received_qty=Decimal("5.000"), despatch_date="2026-09-05",
        )
        # Ordered after the run date: must not appear.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="28", part_code="BT01_015", order_date="2026-09-25", party_code="A009",
            quantity=Decimal("3.000"), received_qty=Decimal("0.000"), despatch_date="2026-09-27",
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:item_wise_pending_report"))
        self.assertContains(response, "Item-Wise Pending P.O.")

    def test_all_items_pending_as_on_run_date(self):
        response = self.client.get(reverse("purchase_orders:item_wise_pending_report_data"), {"run_date": "2026-09-15"})
        groups = {g["part_code"]: g for g in response.json()["groups"]}
        self.assertEqual(list(groups.keys()), ["BT01_015"])  # BT01_020 fully received, PO 28 too late
        line = groups["BT01_015"]["lines"][0]
        self.assertEqual(line["ord_qty"], "10.000")
        self.assertEqual(line["rec_qty"], "2.000")
        self.assertEqual(line["bal_qty"], "8.000")
        self.assertEqual(line["party_name"], "ASSOCIATE BELTING")
        self.assertEqual(line["city"], "Mohali")

    def test_single_item_filter(self):
        response = self.client.get(
            reverse("purchase_orders:item_wise_pending_report_data"), {"run_date": "2026-09-15", "part_code": "BT01_020"},
        )
        self.assertEqual(response.json()["groups"], [])  # BT01_020's only line is fully received

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:item_wise_pending_report_export"), {"run_date": "2026-09-15"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class MonthlyPurchaseReportTablesMixin:
    """cr_out and mrn_dat are the old software's tables (unmanaged); tests create them,
    alongside cust_mst (Party) for the party-name lookup."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Party)
            editor.create_model(CreditorOut)
            editor.create_model(MrnData)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(MrnData)
            editor.delete_model(CreditorOut)
            editor.delete_model(Party)


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class MonthlyPurchaseReportTests(MonthlyPurchaseReportTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="purchase_report_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.vendor = Party.objects.create(party_code="A006", group_code="S002", name="ALFA AUTO ENGG.WORKS")
        MrnData.objects.create(mrn_no="46", amount=Decimal("24212.00"))
        # amt populated: gross amount comes straight from cr_out.amt.
        CreditorOut.objects.create(
            party_code="A006", bill_no="87", bill_date="2026-06-26", mrn_no="46", mrn_date="2026-09-14",
            gross_amount=Decimal("20000.00"), net_amount=Decimal("24212.00"), job_type="",
        )
        # amt empty: gross amount must fall back to mrn_dat.amount (24212.00 above).
        CreditorOut.objects.create(
            party_code="A006", bill_no="88", bill_date="2026-06-26", mrn_no="46", mrn_date="2026-09-14",
            gross_amount=None, net_amount=Decimal("11694.00"), job_type="",
        )
        # Outside the date range: must not appear.
        CreditorOut.objects.create(
            party_code="A006", bill_no="89", bill_date="2026-06-27", mrn_no="49", mrn_date="2026-08-01",
            gross_amount=Decimal("5000.00"), net_amount=Decimal("13034.00"), job_type="",
        )
        # Non-blank job_type: must be excluded even though the date is in range.
        CreditorOut.objects.create(
            party_code="A006", bill_no="90", bill_date="2026-06-27", mrn_no="50", mrn_date="2026-09-14",
            gross_amount=Decimal("9999.00"), net_amount=Decimal("9999.00"), job_type="X",
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:monthly_purchase_report"))
        self.assertContains(response, "Monthly Purchase Report")

    def test_date_range_and_job_type_filter(self):
        response = self.client.get(reverse("purchase_orders:monthly_purchase_report_data"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        rows = response.json()["rows"]
        self.assertEqual(len(rows), 2)  # bill 89 (wrong date) and bill 90 (job_type) excluded
        self.assertEqual({r["bill_no"] for r in rows}, {"87", "88"})

    def test_gross_amount_prefers_cr_out_amt(self):
        response = self.client.get(reverse("purchase_orders:monthly_purchase_report_data"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        rows = {r["bill_no"]: r for r in response.json()["rows"]}
        self.assertEqual(rows["87"]["gross_amount"], "20000.00")

    def test_gross_amount_falls_back_to_mrn_dat(self):
        response = self.client.get(reverse("purchase_orders:monthly_purchase_report_data"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        rows = {r["bill_no"]: r for r in response.json()["rows"]}
        self.assertEqual(rows["88"]["gross_amount"], "24212.00")

    def test_start_after_end_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:monthly_purchase_report_data"), {
            "start_date": "2026-09-30", "end_date": "2026-09-01",
        })
        self.assertEqual(response.status_code, 400)

    def test_no_records_in_range(self):
        response = self.client.get(reverse("purchase_orders:monthly_purchase_report_data"), {
            "start_date": "2020-01-01", "end_date": "2020-01-31",
        })
        self.assertEqual(response.json()["rows"], [])

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:monthly_purchase_report_export"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class ItemWiseRateListTablesMixin:
    """imaster is the old software's table (unmanaged); tests create it, alongside
    cust_mst (Party) and part-mst (Part) which it always references."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Party)
            editor.create_model(Part)
            editor.create_model(ItemMasterTransaction)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            editor.delete_model(ItemMasterTransaction)
            editor.delete_model(Part)
            editor.delete_model(Party)


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class ItemWiseRateListTests(ItemWiseRateListTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="rate_list_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.vendor = Party.objects.create(party_code="A009", group_code="S002", name="ASSOCIATE BELTING", grade="A")
        self.part = Part.objects.create(part_number="BT01_054", description_1="FLAT")
        self.other_part = Part.objects.create(part_number="BT01_017", description_1="DRUM")
        # MRN'd, inside range.
        ItemMasterTransaction.objects.create(
            item_code="BT01_054", party_code="A009", bill_no="696", bill_date="2026-09-10",
            mrn_date="2026-09-11", mrn_flag="Y", quantity=Decimal("10.000"), po_qty=Decimal("10.000"),
            rate=Decimal("155.000"),
        )
        # Not MRN'd: must be excluded.
        ItemMasterTransaction.objects.create(
            item_code="BT01_017", party_code="A009", bill_no="697", bill_date="2026-09-10",
            mrn_date="2026-09-11", mrn_flag="", quantity=Decimal("5.000"), po_qty=Decimal("5.000"),
            rate=Decimal("631.000"),
        )
        # MRN'd but outside the date range: must be excluded.
        ItemMasterTransaction.objects.create(
            item_code="BT01_054", party_code="A009", bill_no="700", bill_date="2026-01-01",
            mrn_date="2026-01-02", mrn_flag="Y", quantity=Decimal("2.000"), po_qty=Decimal("2.000"),
            rate=Decimal("100.000"),
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:item_wise_rate_list"))
        self.assertContains(response, "Item-Wise Rate List")

    def test_all_item_mrn_flag_and_date_filter(self):
        response = self.client.get(reverse("purchase_orders:item_wise_rate_list_data"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        groups = response.json()["groups"]
        self.assertEqual(len(groups), 1)  # only BT01_054's in-range, MRN='Y' row qualifies
        self.assertEqual(groups[0]["item_code"], "BT01_054")
        line = groups[0]["lines"][0]
        self.assertEqual(line["party_name"], "ASSOCIATE BELTING")
        self.assertEqual(line["grade"], "A")
        self.assertEqual(line["qty"], "10.000")
        self.assertEqual(line["po_qty"], "10.000")
        self.assertEqual(line["rate"], "155.00")

    def test_single_item_filter(self):
        response = self.client.get(reverse("purchase_orders:item_wise_rate_list_data"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30", "part_code": "BT01_017",
        })
        self.assertEqual(response.json()["groups"], [])  # BT01_017's only row has mrn_flag=''

    def test_start_after_end_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:item_wise_rate_list_data"), {
            "start_date": "2026-09-30", "end_date": "2026-09-01",
        })
        self.assertEqual(response.status_code, 400)

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:item_wise_rate_list_export"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_print_view_renders(self):
        response = self.client.get(reverse("purchase_orders:item_wise_rate_list_print"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ITEM-WISE RATE LIST")


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class PartyWiseRateListTests(ItemWiseRateListTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="party_rate_list_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.vendor = Party.objects.create(
            party_code="A009", group_code="S002", name="ASSOCIATE BELTING", city="Mohali", grade="A",
        )
        self.other_vendor = Party.objects.create(
            party_code="B003", group_code="S002", name="B.H.MECHANICAL WORKS", city="Ludhiana", grade="B",
        )
        self.part = Part.objects.create(part_number="BT01_054", description_1="FLAT")
        # MRN'd, inside range.
        ItemMasterTransaction.objects.create(
            item_code="BT01_054", party_code="A009", bill_no="696", bill_date="2026-09-10",
            mrn_date="2026-09-11", mrn_flag="Y", quantity=Decimal("10.000"), po_qty=Decimal("10.000"),
            rate=Decimal("155.000"),
        )
        # Not MRN'd: must be excluded.
        ItemMasterTransaction.objects.create(
            item_code="BT01_054", party_code="B003", bill_no="697", bill_date="2026-09-10",
            mrn_date="2026-09-11", mrn_flag="", quantity=Decimal("5.000"), po_qty=Decimal("5.000"),
            rate=Decimal("631.000"),
        )
        # MRN'd but outside the date range: must be excluded.
        ItemMasterTransaction.objects.create(
            item_code="BT01_054", party_code="A009", bill_no="700", bill_date="2026-01-01",
            mrn_date="2026-01-02", mrn_flag="Y", quantity=Decimal("2.000"), po_qty=Decimal("2.000"),
            rate=Decimal("100.000"),
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:party_wise_rate_list"))
        self.assertContains(response, "Party-Wise Rate List")

    def test_all_party_mrn_flag_and_date_filter(self):
        response = self.client.get(reverse("purchase_orders:party_wise_rate_list_data"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        groups = response.json()["groups"]
        self.assertEqual(len(groups), 1)  # only A009's in-range, MRN='Y' row qualifies
        self.assertEqual(groups[0]["party_code"], "A009")
        self.assertEqual(groups[0]["city"], "Mohali")
        self.assertEqual(groups[0]["grade"], "A")
        line = groups[0]["lines"][0]
        self.assertEqual(line["item_name"], "FLAT")
        self.assertEqual(line["qty"], "10.000")
        self.assertEqual(line["po_qty"], "10.000")
        self.assertEqual(line["rate"], "155.00")

    def test_single_party_filter(self):
        response = self.client.get(reverse("purchase_orders:party_wise_rate_list_data"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30", "party_code": "B003",
        })
        self.assertEqual(response.json()["groups"], [])  # B003's only row has mrn_flag=''

    def test_start_after_end_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:party_wise_rate_list_data"), {
            "start_date": "2026-09-30", "end_date": "2026-09-01",
        })
        self.assertEqual(response.status_code, 400)

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:party_wise_rate_list_export"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_print_view_renders(self):
        response = self.client.get(reverse("purchase_orders:party_wise_rate_list_print"), {
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PARTY-WISE RATE LIST")


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class PartyPendingOrderLetterTests(PurchaseOrderTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="letter_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.vendor = Party.objects.create(
            party_code="A009", group_code="S002", name="ASSOCIATE BELTING",
            address_1="Plot 12", address_2="Industrial Area", city="Mohali",
        )
        self.other_vendor = Party.objects.create(party_code="B003", group_code="S002", name="OTHER VENDOR")
        self.part = Part.objects.create(part_number="BT01_015", description_1="FLAT")
        # Still pending.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="27", part_code="BT01_015", order_date="2026-09-05", party_code="A009",
            quantity=Decimal("10.000"), received_qty=Decimal("2.000"), despatch_date="2026-09-12",
        )
        # Fully received: must not appear.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="26", part_code="BT01_015", order_date="2026-08-01", party_code="A009",
            quantity=Decimal("5.000"), received_qty=Decimal("5.000"), despatch_date="2026-08-05",
        )
        # Belongs to a different party: must not appear.
        PurchaseOrderItem.objects.create(
            div="SP", po_no="25", part_code="BT01_015", order_date="2026-09-01", party_code="B003",
            quantity=Decimal("3.000"), received_qty=Decimal("0.000"), despatch_date="2026-09-02",
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:pending_order_letter"))
        self.assertContains(response, "Pending PO Reminder")

    def test_missing_party_code_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:pending_order_letter_data"), {"run_date": "2026-09-20"})
        self.assertEqual(response.status_code, 400)

    def test_only_selected_party_and_pending_lines(self):
        response = self.client.get(reverse("purchase_orders:pending_order_letter_data"), {
            "party_code": "A009", "run_date": "2026-09-20",
        })
        body = response.json()
        self.assertEqual(body["party"]["name"], "ASSOCIATE BELTING")
        self.assertEqual(body["party"]["address_1"], "Plot 12")
        self.assertEqual(len(body["lines"]), 1)  # PO 26 (fully received) and PO 25 (other party) excluded
        line = body["lines"][0]
        self.assertEqual(line["ord_no"], "SP 27")
        self.assertEqual(line["pending_qty"], "8.000")
        self.assertEqual(line["delay_days"], 8)  # 2026-09-20 - 2026-09-12

    def test_order_sorted_by_date_ascending(self):
        PurchaseOrderItem.objects.create(
            div="SP", po_no="20", part_code="BT01_015", order_date="2026-08-20", party_code="A009",
            quantity=Decimal("1.000"), received_qty=Decimal("0.000"), despatch_date="2026-08-22",
        )
        response = self.client.get(reverse("purchase_orders:pending_order_letter_data"), {
            "party_code": "A009", "run_date": "2026-09-20",
        })
        lines = response.json()["lines"]
        self.assertEqual([l["ord_no"] for l in lines], ["SP 20", "SP 27"])

    def test_unknown_party_not_found(self):
        response = self.client.get(reverse("purchase_orders:pending_order_letter_data"), {
            "party_code": "ZZZZ", "run_date": "2026-09-20",
        })
        self.assertEqual(response.status_code, 404)

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:pending_order_letter_export"), {
            "party_code": "A009", "run_date": "2026-09-20",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_print_view_renders_letter(self):
        response = self.client.get(reverse("purchase_orders:pending_order_letter_print"), {
            "party_code": "A009", "run_date": "2026-09-20",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PENDING ORDER")
        self.assertContains(response, "Dear Sir")


@override_settings(COMPANY_STATE_CODE="03", PARTY_CREDITOR_CODE="S002", PARTY_DEBTOR_CODE="S001")
class ItemwisePartyListTests(PurchaseOrderTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="itemwise_party_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.vendor1 = Party.objects.create(party_code="A009", group_code="S002", name="ASSOCIATE BELTING", city="Mohali")
        self.vendor2 = Party.objects.create(party_code="B003", group_code="S002", name="B.H.MECHANICAL WORKS", city="Ludhiana")
        self.part = Part.objects.create(
            part_number="BT01_015", description_1="FLAT",
            supplier_1="A009", rate_1=Decimal("100.0000"),
            supplier_2="B003", rate_2=Decimal("110.0000"),
            supplier_3="",  # blank slot: must be skipped
            supplier_4="ZZZZ", rate_4=Decimal("999.0000"),  # unknown party: must be skipped
        )
        self.bare_part = Part.objects.create(part_number="BT01_020", description_1="DRUM")  # no suppliers at all

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:itemwise_party_list"))
        self.assertContains(response, "Itemwise Party List")

    def test_missing_item_code_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:itemwise_party_list_data"))
        self.assertEqual(response.status_code, 400)

    def test_unknown_item_not_found(self):
        response = self.client.get(reverse("purchase_orders:itemwise_party_list_data"), {"part_code": "NOPE"})
        self.assertEqual(response.status_code, 404)

    def test_rates_never_mixed_and_invalid_slots_skipped(self):
        response = self.client.get(reverse("purchase_orders:itemwise_party_list_data"), {"part_code": "BT01_015"})
        body = response.json()
        self.assertEqual(body["part"], {"code": "BT01_015", "name": "FLAT"})
        rows = body["rows"]
        self.assertEqual(len(rows), 2)  # blank supplier_3 and unknown ZZZZ (supplier_4) skipped
        by_code = {r["party_code"]: r for r in rows}
        self.assertEqual(by_code["A009"]["rate"], "100.00")
        self.assertEqual(by_code["A009"]["party_name"], "ASSOCIATE BELTING")
        self.assertEqual(by_code["A009"]["city"], "Mohali")
        self.assertEqual(by_code["B003"]["rate"], "110.00")
        self.assertEqual(by_code["B003"]["party_name"], "B.H.MECHANICAL WORKS")

    def test_item_with_no_suppliers_returns_empty_rows(self):
        response = self.client.get(reverse("purchase_orders:itemwise_party_list_data"), {"part_code": "BT01_020"})
        self.assertEqual(response.json()["rows"], [])

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:itemwise_party_list_export"), {"part_code": "BT01_015"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_excel_export_without_item_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:itemwise_party_list_export"))
        self.assertEqual(response.status_code, 400)

    def test_print_view_renders(self):
        response = self.client.get(reverse("purchase_orders:itemwise_party_list_print"), {"part_code": "BT01_015"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ITEMWISE PARTY LIST")


class PartyWiseItemListTests(PurchaseOrderTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="party_wise_item_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.user)
        self.party = Party.objects.create(party_code="A009", group_code="S002", name="ASSOCIATE BELTING", grade="A")
        Party.objects.create(party_code="B003", group_code="S002", name="OTHER VENDOR")
        # matches via supplier_1 -> rate_1
        Part.objects.create(part_number="BT01_015", description_1="FLAT", supplier_1="A009", rate_1=Decimal("100.0000"))
        # matches via supplier_3 -> rate_3 (never mixed with rate_1/rate_2)
        Part.objects.create(part_number="BT01_020", description_1="DRUM", supplier_3="A009", rate_3=Decimal("250.0000"))
        # no match at all
        Part.objects.create(part_number="BT01_030", description_1="ROLLER", supplier_1="B003", rate_1=Decimal("999.0000"))

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:party_wise_item_list"))
        self.assertContains(response, "Party Wise Item List")

    def test_missing_party_code_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:party_wise_item_list_data"))
        self.assertEqual(response.status_code, 400)

    def test_unknown_party_not_found(self):
        response = self.client.get(reverse("purchase_orders:party_wise_item_list_data"), {"party_code": "NOPE"})
        self.assertEqual(response.status_code, 404)

    def test_matches_correct_slot_rate_and_orders_by_code(self):
        response = self.client.get(reverse("purchase_orders:party_wise_item_list_data"), {"party_code": "A009"})
        body = response.json()
        self.assertEqual(body["party"], {"code": "A009", "name": "ASSOCIATE BELTING", "grade": "A"})
        rows = body["rows"]
        self.assertEqual([r["code"] for r in rows], ["BT01_015", "BT01_020"])
        self.assertEqual(rows[0]["rate"], "100.00")
        self.assertEqual(rows[1]["rate"], "250.00")

    def test_party_with_no_items_returns_empty_rows(self):
        Party.objects.create(party_code="C001", group_code="S002", name="NO ITEMS VENDOR")
        response = self.client.get(reverse("purchase_orders:party_wise_item_list_data"), {"party_code": "C001"})
        self.assertEqual(response.json()["rows"], [])

    def test_excel_export_downloads(self):
        response = self.client.get(reverse("purchase_orders:party_wise_item_list_export"), {"party_code": "A009"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_excel_export_without_party_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:party_wise_item_list_export"))
        self.assertEqual(response.status_code, 400)


class PurchaseOrderAdjustmentTests(PurchaseOrderTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_user(username="poa_editor", password="S3cure-pass!")
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_purchase_order"))
        cls.viewer = get_user_model().objects.create_user(username="poa_viewer", password="S3cure-pass!")

    def setUp(self):
        self.client.force_login(self.editor)
        self.party = Party.objects.create(party_code="A009", group_code="S002", name="ASSOCIATE BELTING")
        Part.objects.create(part_number="BT01_015", description_1="FLAT")
        # pending: qty > rec, not adjusted -> should appear
        self.pending_line = PurchaseOrderItem.objects.create(
            div="SP", po_no="0001", party_code="A009", part_code="BT01_015",
            order_date=date(2026, 1, 1), quantity=Decimal("10"), received_qty=Decimal("4"), adjusted="",
        )
        # fully received -> pending <= 0, must be excluded
        PurchaseOrderItem.objects.create(
            div="SP", po_no="0002", party_code="A009", part_code="BT01_015",
            order_date=date(2026, 1, 2), quantity=Decimal("5"), received_qty=Decimal("5"), adjusted="",
        )
        # already adjusted -> must be excluded
        PurchaseOrderItem.objects.create(
            div="SP", po_no="0003", party_code="A009", part_code="BT01_015",
            order_date=date(2026, 1, 3), quantity=Decimal("8"), received_qty=Decimal("1"), adjusted="Y",
        )

    def save(self, party_code, rows, as_user=None):
        self.client.force_login(as_user or self.editor)
        return self.client.post(
            reverse("purchase_orders:po_adjustment_save"),
            data=json.dumps({"party_code": party_code, "rows": rows}),
            content_type="application/json",
        )

    def test_page_renders(self):
        response = self.client.get(reverse("purchase_orders:po_adjustment"))
        self.assertContains(response, "Pending Purchase Order Adjustment")

    def test_missing_party_code_is_rejected(self):
        response = self.client.get(reverse("purchase_orders:po_adjustment_data"))
        self.assertEqual(response.status_code, 400)

    def test_unknown_party_not_found(self):
        response = self.client.get(reverse("purchase_orders:po_adjustment_data"), {"party_code": "NOPE"})
        self.assertEqual(response.status_code, 404)

    def test_only_pending_unadjusted_rows_returned(self):
        response = self.client.get(reverse("purchase_orders:po_adjustment_data"), {"party_code": "A009"})
        body = response.json()
        self.assertEqual(body["party"], {"code": "A009", "name": "ASSOCIATE BELTING"})
        rows = body["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["po_no"], "0001")
        self.assertEqual(rows[0]["item_name"], "FLAT")
        self.assertEqual(rows[0]["pending"], "6.000")

    def test_confirm_writes_adj_onto_matching_line_only(self):
        response = self.save("A009", [{"po_no": "0001", "div": "SP", "part_code": "BT01_015", "adj": "Y"}])
        self.assertEqual(response.status_code, 200, response.content)
        self.pending_line.refresh_from_db()
        self.assertEqual(self.pending_line.adjusted, "Y")

    def test_confirm_never_touches_already_adjusted_row(self):
        response = self.save("A009", [{"po_no": "0003", "div": "SP", "part_code": "BT01_015", "adj": "X"}])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["updated"], 0)
        self.assertEqual(len(response.json()["skipped"]), 1)

    def test_save_requires_party(self):
        response = self.save("", [{"po_no": "0001", "div": "SP", "part_code": "BT01_015", "adj": "Y"}])
        self.assertEqual(response.status_code, 400)

    def test_viewer_without_permission_cannot_save(self):
        response = self.save("A009", [{"po_no": "0001", "div": "SP", "part_code": "BT01_015", "adj": "Y"}], as_user=self.viewer)
        self.assertEqual(response.status_code, 403)
        self.pending_line.refresh_from_db()
        self.assertEqual(self.pending_line.adjusted, "")

    def test_login_required(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("purchase_orders:po_adjustment")).status_code, 200)

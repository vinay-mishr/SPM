import json
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.items.models import Item
from apps.parts.models import Part
from apps.parties.models import Party

from . import services
from .models import BomComponent, BomSaComponent


class ConMstTableMixin:
    """item, part-mst, con-mst and conms are the old software's tables (unmanaged); tests create them."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(Item)
            editor.create_model(Party)
        with connection.cursor() as cursor:
            # Like the real part-mst: no primary key / unique constraint (part numbers repeat).
            cursor.execute(
                'CREATE TABLE "part-mst" (icod varchar(10), ides varchar(35), rname1 varchar(35), '
                "qnty decimal(11,3), drgno varchar(10), gauge varchar(10), std_pack decimal(5,0), "
                "grade varchar(2), g_wt decimal(10,4), rate decimal(10,4), srate decimal(10,2), "
                "op_stk decimal(12,3), rop decimal(11,3), material varchar(15), wt decimal(7,3), "
                "cur_stk decimal(10,0), loc varchar(10), uom varchar(3), hs_code varchar(8), "
                "gs_rt decimal(5,2), s_cod varchar(1), item_type varchar(1), party1 varchar(4), "
                "rate1 decimal(10,4), party2 varchar(4), rate2 decimal(10,4), party3 varchar(4), "
                "rate3 decimal(10,4), party4 varchar(4), rate4 decimal(10,4), uname varchar(10))"
            )
            # Like the real con-mst: no key at all (icod + item can repeat). Belongs only to
            # the plain, Item-wise Bill of Material Master screen.
            cursor.execute(
                'CREATE TABLE "con-mst" (icod varchar(10), item varchar(10), qty decimal(12,5), '
                "unit varchar(2), time_req decimal(10,2), uname varchar(10))"
            )
            # Like the real conms: a separate physical table, no key at all. Belongs only to
            # the Bill of Material Master (Sub Assembly) screen.
            cursor.execute(
                'CREATE TABLE "conms" (icod varchar(10), item varchar(10), qty decimal(12,5), '
                "unit varchar(2), time_req decimal(10,2), uname varchar(10))"
            )
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.cursor() as cursor:
            cursor.execute('DROP TABLE "conms"')
            cursor.execute('DROP TABLE "con-mst"')
            cursor.execute('DROP TABLE "part-mst"')
        with connection.schema_editor() as editor:
            editor.delete_model(Party)
            editor.delete_model(Item)


class BomMasterTests(ConMstTableMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_user(username="bom_editor", password="S3cure-pass!")
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_bom"))
        cls.viewer = get_user_model().objects.create_user(username="bom_viewer", password="S3cure-pass!")

    def setUp(self):
        Part.objects.create(part_number="ABM01", description_1="INFEED ASSY", unit="SET")
        Part.objects.create(part_number="ABM02", description_1="OUTFEED ASSY")
        Part.objects.create(part_number="ABM01_001", description_1="FLAT", unit="PCS")
        Part.objects.create(part_number="ABM01_002", description_1="DRUM")
        Part.objects.create(part_number="DUPX", description_1="DUP ONE")
        Part.objects.create(part_number="DUPX", description_1="DUP TWO")

    def save(self, part_code, components, as_user=None):
        self.client.force_login(as_user or self.editor)
        return self.client.post(
            reverse("bom:api_save"),
            data=json.dumps({"part_code": part_code, "components": components}),
            content_type="application/json",
        )

    def test_grid_shows_reference_columns(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("bom:master"))
        for heading in ("Part Code", "Item Name", "Unit", "Quantity"):
            self.assertContains(response, heading)

    def test_save_creates_component_rows(self):
        response = self.save("abm01", [
            {"item_code": "abm01_001", "quantity": "2"},
            {"item_code": "abm01_002", "quantity": "1.5"},
        ])
        self.assertEqual(response.status_code, 200, response.content)
        rows = list(
            BomSaComponent.objects.filter(parent_part_code="ABM01")
            .order_by("component_part_code").values_list("component_part_code", "quantity")
        )
        self.assertEqual(rows, [("ABM01_001", Decimal("2.00000")), ("ABM01_002", Decimal("1.50000"))])

    def test_save_replaces_existing_set(self):
        self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "2"}])
        self.save("ABM01", [{"item_code": "ABM01_002", "quantity": "5"}])
        rows = list(BomSaComponent.objects.filter(parent_part_code="ABM01").values_list("component_part_code", flat=True))
        self.assertEqual(rows, ["ABM01_002"])

    def test_unknown_part_rejected(self):
        response = self.save("NOSUCH", [{"item_code": "ABM01_001", "quantity": "1"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("part_code", response.json()["errors"])
        self.assertFalse(BomSaComponent.objects.exists())

    def test_unknown_item_rejected(self):
        response = self.save("ABM01", [{"item_code": "ZZZZ", "quantity": "1"}])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BomSaComponent.objects.exists())

    def test_negative_or_zero_quantity_rejected(self):
        self.assertEqual(self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "0"}]).status_code, 400)
        self.assertEqual(self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "-1"}]).status_code, 400)
        self.assertFalse(BomSaComponent.objects.exists())

    def test_duplicate_item_in_same_save_rejected(self):
        response = self.save("ABM01", [
            {"item_code": "ABM01_001", "quantity": "1"}, {"item_code": "ABM01_001", "quantity": "2"},
        ])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BomSaComponent.objects.exists())

    def test_self_reference_rejected(self):
        response = self.save("ABM01", [{"item_code": "ABM01", "quantity": "1"}])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BomSaComponent.objects.exists())

    def test_ambiguous_part_number_blocked(self):
        response = self.save("DUPX", [{"item_code": "ABM01_001", "quantity": "1"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("ambiguous", response.json()["errors"]["part_code"])

    def test_no_components_rejected(self):
        response = self.save("ABM01", [])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BomSaComponent.objects.exists())

    def test_detail_endpoint_returns_item_names(self):
        self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "2"}])
        self.client.force_login(self.editor)
        response = self.client.get(reverse("bom:api_detail", args=["ABM01"]))
        self.assertEqual(response.json()["components"], [
            {"item_code": "ABM01_001", "item_name": "FLAT", "quantity": "2.000", "unit": "", "is_duplicate": False}
        ])

    def test_list_includes_parent_unit(self):
        self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "2"}])
        self.client.force_login(self.editor)
        response = self.client.get(reverse("bom:api_list"))
        row = next(p for p in response.json()["parents"] if p["part_code"] == "ABM01")
        self.assertEqual(row["unit"], "SET")

    def test_delete_removes_all_rows_for_part(self):
        self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "1"}, {"item_code": "ABM01_002", "quantity": "1"}])
        response = self.client.post(reverse("bom:api_delete", args=["ABM01"]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BomSaComponent.objects.filter(parent_part_code="ABM01").exists())

    def test_delete_ambiguous_part_blocked(self):
        BomSaComponent.objects.create(parent_part_code="DUPX", component_part_code="ABM01_001", quantity=Decimal("1"))
        self.client.force_login(self.editor)
        response = self.client.post(reverse("bom:api_delete", args=["DUPX"]))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(BomSaComponent.objects.filter(parent_part_code="DUPX").exists())

    def test_part_and_item_search(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("bom:api_parts"), {"q": "infeed"})
        self.assertEqual([p["code"] for p in response.json()["parts"]], ["ABM01"])

    def test_search_parts_includes_unit(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("bom:api_parts"), {"q": "infeed"})
        self.assertEqual(response.json()["parts"][0]["unit"], "SET")

    def test_save_stores_unit_widened_to_three_chars(self):
        response = self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "2", "unit": "PCS"}])
        self.assertEqual(response.status_code, 200, response.content)
        row = BomSaComponent.objects.get(parent_part_code="ABM01", component_part_code="ABM01_001")
        self.assertEqual(row.unit, "PCS")
        self.client.force_login(self.editor)
        detail = self.client.get(reverse("bom:api_detail", args=["ABM01"]))
        self.assertEqual(detail.json()["components"][0]["unit"], "PCS")

    def test_viewer_without_permission_cannot_save(self):
        response = self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "1"}], as_user=self.viewer)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BomSaComponent.objects.exists())

    def test_writes_disabled_blocks_save(self):
        from unittest import mock
        with mock.patch.object(services, "writes_enabled", return_value=False):
            response = self.save("ABM01", [{"item_code": "ABM01_001", "quantity": "1"}])
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BomSaComponent.objects.exists())

    def test_login_required(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("bom:master")).status_code, 200)


class BomItemMasterTests(ConMstTableMixin, TestCase):
    """Same con-mst table as BomMasterTests, roles reversed: Item = parent, Part = component."""

    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_user(username="bomi_editor", password="S3cure-pass!")
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_bom"))
        cls.viewer = get_user_model().objects.create_user(username="bomi_viewer", password="S3cure-pass!")

    def setUp(self):
        Part.objects.create(part_number="ABM01_001", description_1="FLAT")
        Part.objects.create(part_number="ABM01_002", description_1="DRUM")
        Part.objects.create(part_number="DUPX", description_1="DUP ONE")
        Part.objects.create(part_number="DUPX", description_1="DUP TWO")
        Item.objects.create(item_code="0011", item_name_1="CONVEYOR L 4' W 114MM")
        Item.objects.create(item_code="0020", item_name_1="AUTOMATIC BINDING MACHINE")

    def save(self, item_code, components, as_user=None):
        self.client.force_login(as_user or self.editor)
        return self.client.post(
            reverse("bom:api_item_save"),
            data=json.dumps({"item_code": item_code, "components": components}),
            content_type="application/json",
        )

    def test_grid_shows_reference_columns(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("bom:item_master"))
        for heading in ("Item Code", "Item Name", "Quantity"):
            self.assertContains(response, heading)

    def test_save_creates_component_rows(self):
        response = self.save("0011", [
            {"part_code": "abm01_001", "quantity": "2"},
            {"part_code": "abm01_002", "quantity": "1.5"},
        ])
        self.assertEqual(response.status_code, 200, response.content)
        rows = list(BomComponent.objects.filter(item_code="0011").order_by("part_code").values_list("part_code", "quantity"))
        self.assertEqual(rows, [("ABM01_001", Decimal("2.00000")), ("ABM01_002", Decimal("1.50000"))])

    def test_save_replaces_existing_set(self):
        self.save("0011", [{"part_code": "ABM01_001", "quantity": "2"}])
        self.save("0011", [{"part_code": "ABM01_002", "quantity": "5"}])
        rows = list(BomComponent.objects.filter(item_code="0011").values_list("part_code", flat=True))
        self.assertEqual(rows, ["ABM01_002"])

    def test_unknown_item_rejected(self):
        response = self.save("NOSUCH", [{"part_code": "ABM01_001", "quantity": "1"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("item_code", response.json()["errors"])
        self.assertFalse(BomComponent.objects.exists())

    def test_unknown_part_rejected(self):
        response = self.save("0011", [{"part_code": "ZZZZ", "quantity": "1"}])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BomComponent.objects.exists())

    def test_ambiguous_part_rejected(self):
        response = self.save("0011", [{"part_code": "DUPX", "quantity": "1"}])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BomComponent.objects.exists())

    def test_negative_or_zero_quantity_rejected(self):
        self.assertEqual(self.save("0011", [{"part_code": "ABM01_001", "quantity": "0"}]).status_code, 400)
        self.assertEqual(self.save("0011", [{"part_code": "ABM01_001", "quantity": "-1"}]).status_code, 400)
        self.assertFalse(BomComponent.objects.exists())

    def test_duplicate_part_in_same_save_rejected(self):
        response = self.save("0011", [
            {"part_code": "ABM01_001", "quantity": "1"}, {"part_code": "ABM01_001", "quantity": "2"},
        ])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BomComponent.objects.exists())

    def test_no_components_rejected(self):
        response = self.save("0011", [])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BomComponent.objects.exists())

    def test_detail_endpoint_returns_part_names(self):
        self.save("0011", [{"part_code": "ABM01_001", "quantity": "2"}])
        self.client.force_login(self.editor)
        response = self.client.get(reverse("bom:api_item_detail", args=["0011"]))
        self.assertEqual(response.json()["components"], [
            {"part_code": "ABM01_001", "part_name": "FLAT", "quantity": "2.000", "unit": "", "is_duplicate": False}
        ])

    def test_delete_removes_all_rows_for_item(self):
        self.save("0011", [{"part_code": "ABM01_001", "quantity": "1"}, {"part_code": "ABM01_002", "quantity": "1"}])
        response = self.client.post(reverse("bom:api_item_delete", args=["0011"]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BomComponent.objects.filter(item_code="0011").exists())

    def test_no_cross_listing_with_sa_screen(self):
        """con-mst (this screen) and conms (the Sub-Assembly screen) are separate physical
        tables, confirmed by querying the live legacy database -- a BOM saved here never
        shows up in the SA screen's own list."""
        self.save("0011", [{"part_code": "ABM01_001", "quantity": "2"}])
        sa_parents = [p["part_code"] for p in services.list_parents()]
        self.assertNotIn("ABM01_001", sa_parents)

    def test_viewer_without_permission_cannot_save(self):
        response = self.save("0011", [{"part_code": "ABM01_001", "quantity": "1"}], as_user=self.viewer)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BomComponent.objects.exists())

    def test_login_required(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("bom:item_master")).status_code, 200)


class ConsumptionMasterTests(ConMstTableMixin, TestCase):
    """Read-only report: for one item, its BOM components with Part Master reference
    fields and computed Value = qty * Part.purchase_rate (old VFP "CONSUMPTION MASTER",
    ITEMLIST.PRN print / Excel export)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="cm_user", password="S3cure-pass!")

    def setUp(self):
        Item.objects.create(item_code="0049", item_name_1="WRAPPING MCHINE TOILET 2SERVO")
        Part.objects.create(
            part_number="WM01", description_1="CUT OFF ASSY DOUBLE TOILT",
            material="MS", weight_by_100=Decimal("0"), gauge="", drawing_no="", purchase_rate=Decimal("50000"),
        )
        Part.objects.create(
            part_number="WM02", description_1="DISCHARGE ASSY",
            material="", weight_by_100=Decimal("0"), gauge="", drawing_no="", purchase_rate=Decimal("0"),
        )
        BomComponent.objects.create(item_code="0049", part_code="WM01", quantity=Decimal("1"))
        BomComponent.objects.create(item_code="0049", part_code="WM02", quantity=Decimal("1"))

    def test_data_endpoint_returns_lines_and_total(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:consumption_master_data"), {"item_code": "0049"})
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["item_code"], "0049")
        self.assertEqual(body["item_name"], "WRAPPING MCHINE TOILET 2SERVO")
        self.assertEqual(len(body["lines"]), 2)
        self.assertEqual(body["lines"][0]["code"], "WM01")
        self.assertEqual(body["lines"][0]["value"], "50000.00")
        self.assertEqual(body["total"], "50000.00")

    def test_item_with_no_components(self):
        Item.objects.create(item_code="0099", item_name_1="NO BOM ITEM")
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:consumption_master_data"), {"item_code": "0099"})
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["lines"], [])
        self.assertEqual(body["total"], "0.00")

    def test_unknown_item_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:consumption_master_data"), {"item_code": "ZZZZ"})
        self.assertEqual(response.status_code, 404)

    def test_export_matches_page_data(self):
        from openpyxl import load_workbook
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:consumption_master_export"), {"item_code": "0049"})
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.content))
        ws = wb.active
        self.assertIn("WRAPPING MCHINE TOILET 2SERVO", ws.cell(row=3, column=1).value)
        self.assertEqual(ws.cell(row=6, column=2).value, "WM01")
        self.assertEqual(ws.cell(row=6, column=9).value, 50000.0)
        self.assertEqual(ws.cell(row=8, column=9).value, 50000.0)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("bom:consumption_master"))
        self.assertNotEqual(response.status_code, 200)


class BomWithoutValueTests(ConMstTableMixin, TestCase):
    """Same report as Consumption Master, but no Rate/Value/Total at all (old VFP screen's
    "Without Value" Excel button)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="wov_user", password="S3cure-pass!")

    def setUp(self):
        Item.objects.create(item_code="0007", item_name_1="FLOW WRAP M/C WITH COLATOR")
        Part.objects.create(
            part_number="CO01", description_1="COLLATOR ASSY",
            material="M.S", weight_by_100=Decimal("0"), gauge="", drawing_no="", purchase_rate=Decimal("999"),
        )
        BomComponent.objects.create(item_code="0007", part_code="CO01", quantity=Decimal("1"))

    def test_data_has_no_value_field(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:without_value_data"), {"item_code": "0007"})
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["item_code"], "0007")
        self.assertEqual(len(body["lines"]), 1)
        self.assertEqual(body["lines"][0]["code"], "CO01")
        self.assertEqual(body["lines"][0]["material"], "M.S")
        self.assertNotIn("value", body["lines"][0])
        self.assertNotIn("total", body)

    def test_item_with_no_components(self):
        Item.objects.create(item_code="0099", item_name_1="NO BOM ITEM")
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:without_value_data"), {"item_code": "0099"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["lines"], [])

    def test_unknown_item_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:without_value_data"), {"item_code": "ZZZZ"})
        self.assertEqual(response.status_code, 404)

    def test_export_has_no_value_column(self):
        from openpyxl import load_workbook
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:without_value_export"), {"item_code": "0007"})
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.content))
        ws = wb.active
        headers = [ws.cell(row=5, column=c).value for c in range(1, 10)]
        self.assertEqual(
            headers,
            ["Sno", "Code", "Item Description", "Qty", "Unit", "Material", "Wt/100", "Gauge", "Drawing No"],
        )
        self.assertIsNone(ws.cell(row=5, column=10).value)
        self.assertEqual(ws.cell(row=6, column=2).value, "CO01")
        self.assertIsNone(ws.cell(row=6, column=10).value)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("bom:without_value"))
        self.assertNotEqual(response.status_code, 200)


class SaValueWiseTests(ConMstTableMixin, TestCase):
    """Bill of Material Master Value-Wise (Sub Assembly): reads conms (BomSaComponent),
    Part Master parent (not Item Master), Value = Qty * Part.purchase_rate."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="svw_user", password="S3cure-pass!")

    def setUp(self):
        Part.objects.create(part_number="ABM01", description_1="INFEED ASSY", unit="SET")
        Part.objects.create(
            part_number="ABM01_001", description_1="FLAT", hsn_code="8445", material="M.S",
            purchase_rate=Decimal("1500"), sale_rate=Decimal("3100"), drawing_no="ABM01_001", unit="PCS",
        )
        BomSaComponent.objects.create(parent_part_code="ABM01", component_part_code="ABM01_001", quantity=Decimal("2"), unit="PCS")

    def test_data_returns_value_wise_lines_and_total(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_value_wise_data"), {"part_code": "ABM01"})
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["item_code"], "ABM01")
        self.assertEqual(body["item_name"], "INFEED ASSY")
        self.assertNotIn("unit", body)
        line = body["lines"][0]
        self.assertEqual(line["code"], "ABM01_001")
        self.assertEqual(line["hsn_code"], "8445")
        self.assertEqual(line["quantity"], "2.000")
        self.assertEqual(line["unit"], "PCS")
        self.assertEqual(line["material"], "M.S")
        self.assertEqual(line["purchase_rate"], "1500.000")
        self.assertEqual(line["sale_rate"], "3100.00")
        self.assertEqual(line["value"], "3000.00")
        self.assertEqual(body["total"], "3000.00")

    def test_value_uses_purchase_rate_not_sale_rate(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_value_wise_data"), {"part_code": "ABM01"})
        body = response.json()["data"]
        self.assertEqual(body["lines"][0]["value"], "3000.00")

    def test_part_with_no_components(self):
        Part.objects.create(part_number="ABM99", description_1="NO BOM PART")
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_value_wise_data"), {"part_code": "ABM99"})
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["lines"], [])
        self.assertEqual(body["total"], "0.00")

    def test_unknown_part_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_value_wise_data"), {"part_code": "ZZZZ"})
        self.assertEqual(response.status_code, 404)

    def test_export_matches_page_data(self):
        from openpyxl import load_workbook
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_value_wise_export"), {"part_code": "ABM01"})
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.content))
        ws = wb.active
        headers = [ws.cell(row=5, column=c).value for c in range(1, 12)]
        self.assertEqual(headers, [
            "Sno", "Code", "Item Description", "Hsn code", "Qty", "Unit",
            "Material", "P.RATE", "S.RATE", "Drawing No", "Value(in Rs)",
        ])
        self.assertEqual(ws.cell(row=6, column=2).value, "ABM01_001")
        self.assertEqual(ws.cell(row=6, column=11).value, 3000.0)
        self.assertEqual(ws.cell(row=7, column=11).value, 3000.0)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("bom:sa_value_wise"))
        self.assertNotEqual(response.status_code, 200)


class SaSuppliersTests(ConMstTableMixin, TestCase):
    """Bill of Material Master Suppliers (Sub Assembly, no value): reads conms with a Part
    Master parent, and resolves each component's Supplier-1..4 party codes to names via
    the existing Party Master -- no value/rate columns at all."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="sup_user", password="S3cure-pass!")

    def setUp(self):
        Party.objects.create(party_code="S001", name="S.A.T HYGIENES")
        Party.objects.create(party_code="S002", name="AMAN INDUSTRIES")
        Part.objects.create(part_number="ABM01", description_1="INFEED ASSY", unit="SET")
        Part.objects.create(
            part_number="ABM01_001", description_1="FLAT", material="M.S",
            supplier_1="S001", supplier_2="S002",
        )
        BomSaComponent.objects.create(parent_part_code="ABM01", component_part_code="ABM01_001", quantity=Decimal("1"))

    def test_data_resolves_supplier_names(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_suppliers_data"), {"part_code": "ABM01"})
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["item_code"], "ABM01")
        self.assertEqual(body["item_name"], "INFEED ASSY")
        self.assertEqual(body["unit"], "SET")
        self.assertNotIn("total", body)
        line = body["lines"][0]
        self.assertEqual(line["code"], "ABM01_001")
        self.assertEqual(line["material"], "M.S")
        self.assertEqual(line["supplier_1"], "S.A.T HYGIENES")
        self.assertEqual(line["supplier_2"], "AMAN INDUSTRIES")
        self.assertEqual(line["supplier_3"], "")
        self.assertEqual(line["supplier_4"], "")
        self.assertNotIn("value", line)
        self.assertNotIn("hsn_code", line)

    def test_missing_supplier_left_blank_no_crash(self):
        Part.objects.create(part_number="ABM01_002", description_1="DRUM", supplier_1="NOSUCH")
        BomSaComponent.objects.create(parent_part_code="ABM01", component_part_code="ABM01_002", quantity=Decimal("1"))
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_suppliers_data"), {"part_code": "ABM01"})
        self.assertEqual(response.status_code, 200)
        line = next(l for l in response.json()["data"]["lines"] if l["code"] == "ABM01_002")
        self.assertEqual(line["supplier_1"], "")

    def test_part_with_no_components(self):
        Part.objects.create(part_number="ABM99", description_1="NO BOM PART")
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_suppliers_data"), {"part_code": "ABM99"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["lines"], [])

    def test_unknown_part_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_suppliers_data"), {"part_code": "ZZZZ"})
        self.assertEqual(response.status_code, 404)

    def test_export_has_no_value_columns(self):
        from openpyxl import load_workbook
        self.client.force_login(self.user)
        response = self.client.get(reverse("bom:sa_suppliers_export"), {"part_code": "ABM01"})
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.content))
        ws = wb.active
        self.assertEqual(ws.cell(row=5, column=1).value, "Unit : SET")
        headers = [ws.cell(row=6, column=c).value for c in range(1, 10)]
        self.assertEqual(headers, [
            "Sno", "Code", "Item Description", "Qty", "Material",
            "Supplier-1", "Supplier-2", "Supplier-3", "Supplier-4",
        ])
        self.assertEqual(ws.cell(row=7, column=6).value, "S.A.T HYGIENES")
        self.assertEqual(ws.cell(row=7, column=7).value, "AMAN INDUSTRIES")

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("bom:sa_suppliers"))
        self.assertNotEqual(response.status_code, 200)

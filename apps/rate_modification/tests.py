import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.parts.models import Part

from . import services


class RateModificationTests(TestCase):
    """part-mst is the old software's table (unmanaged, no real primary key); tests create it."""

    @classmethod
    def setUpClass(cls):
        with connection.cursor() as cursor:
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
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.cursor() as cursor:
            cursor.execute('DROP TABLE "part-mst"')

    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_user(username="rate_editor", password="S3cure-pass!")
        cls.editor.user_permissions.add(Permission.objects.get(codename="change_rate"))
        cls.viewer = get_user_model().objects.create_user(username="rate_viewer", password="S3cure-pass!")

    def setUp(self):
        Part.objects.create(
            part_number="ABM01", description_1="INFEED ASSY", hsn_code="8485",
            gst_percent=Decimal("18"), purchase_rate=Decimal("0"), opening_stock=Decimal("1"),
            current_stock=Decimal("1"), supplier_1="S048",
        )
        Part.objects.create(
            part_number="ABM01_001", description_1="FLAT", drawing_no="ABM01_001", hsn_code="8445",
            gst_percent=Decimal("18"), purchase_rate=Decimal("1500"), sale_rate=Decimal("3100"),
            opening_stock=Decimal("0"), current_stock=Decimal("0"), location="RACK 9",
            supplier_1="S048", rate_1=Decimal("1500"),
        )
        # A duplicate part number, like the 3 real ones in part-mst: must be write-protected.
        Part.objects.create(part_number="DUPX", description_1="DUP ONE", purchase_rate=Decimal("10"))
        Part.objects.create(part_number="DUPX", description_1="DUP TWO", purchase_rate=Decimal("20"))

    def save(self, changes, as_user=None):
        self.client.force_login(as_user or self.editor)
        return self.client.post(
            reverse("rate_modification:api_save"),
            data=json.dumps({"changes": changes}),
            content_type="application/json",
        )

    def test_grid_shows_reference_columns(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("rate_modification:master"))
        for heading in ("Code", "Item Name", "Rate", "Op. Stk", "Cur. Stk", "GST%", "Location"):
            self.assertContains(response, heading)
        rows = self.client.get(reverse("rate_modification:api_data")).json()["rows"]
        codes = [r["code"] for r in rows]
        self.assertIn("ABM01", codes)
        row = next(r for r in rows if r["code"] == "ABM01_001")
        self.assertEqual(row, {
            "id": "ABM01_001", "code": "ABM01_001", "name": "FLAT", "rate": "1500.00",
            "opening_stock": "0.00", "current_stock": "0.00", "gst_percent": "18.00",
            "location": "RACK 9",
        })

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("rate_modification:master"))
        self.assertNotEqual(response.status_code, 200)
        response = self.client.post(
            reverse("rate_modification:api_save"),
            data=json.dumps({"changes": [{"code": "ABM01", "rate": "5"}]}),
            content_type="application/json",
        )
        self.assertNotEqual(response.status_code, 200)

    def test_save_changes_only_the_rate_column(self):
        before = Part.objects.get(part_number="ABM01_001")
        response = self.save([{"code": "ABM01_001", "rate": "1650.75"}])
        self.assertEqual(response.status_code, 200)

        after = Part.objects.get(part_number="ABM01_001")
        self.assertEqual(after.purchase_rate, Decimal("1650.7500"))
        # Every other field must be byte-for-byte unchanged.
        self.assertEqual(after.description_1, before.description_1)
        self.assertEqual(after.hsn_code, before.hsn_code)
        self.assertEqual(after.gst_percent, before.gst_percent)
        self.assertEqual(after.opening_stock, before.opening_stock)
        self.assertEqual(after.current_stock, before.current_stock)
        self.assertEqual(after.location, before.location)
        self.assertEqual(after.supplier_1, before.supplier_1)
        self.assertEqual(after.rate_1, before.rate_1)
        self.assertEqual(after.sale_rate, before.sale_rate)

    def test_save_rejects_negative_rate(self):
        response = self.save([{"code": "ABM01", "rate": "-5"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("ABM01", response.json()["errors"])
        self.assertEqual(Part.objects.get(part_number="ABM01").purchase_rate, Decimal("0"))

    def test_save_rejects_non_numeric_rate(self):
        response = self.save([{"code": "ABM01", "rate": "abc"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("ABM01", response.json()["errors"])

    def test_save_rejects_blank_rate(self):
        response = self.save([{"code": "ABM01", "rate": ""}])
        self.assertEqual(response.status_code, 400)

    def test_save_unknown_part_reports_error(self):
        response = self.save([{"code": "NOSUCH", "rate": "5"}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["NOSUCH"], "Part not found.")

    def test_duplicate_part_number_blocked(self):
        response = self.save([{"code": "DUPX", "rate": "99"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("more than once", response.json()["errors"]["DUPX"])
        self.assertListEqual(
            sorted(Part.objects.filter(part_number="DUPX").values_list("purchase_rate", flat=True)),
            [Decimal("10.0000"), Decimal("20.0000")],
        )

    def test_all_or_nothing_when_one_row_invalid(self):
        response = self.save([{"code": "ABM01", "rate": "250"}, {"code": "ABM01_001", "rate": "-1"}])
        self.assertEqual(response.status_code, 400)
        # ABM01's valid change must NOT have been applied since ABM01_001 failed.
        self.assertEqual(Part.objects.get(part_number="ABM01").purchase_rate, Decimal("0"))

    def test_viewer_without_permission_cannot_save(self):
        response = self.save([{"code": "ABM01", "rate": "250"}], as_user=self.viewer)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Part.objects.get(part_number="ABM01").purchase_rate, Decimal("0"))

    def test_viewer_sees_read_only_page(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("rate_modification:master"))
        self.assertContains(response, "View only")

    def test_writes_disabled_blocks_save(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            response = self.save([{"code": "ABM01", "rate": "250"}])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Part.objects.get(part_number="ABM01").purchase_rate, Decimal("0"))

    def test_parse_rate_helper(self):
        self.assertEqual(services.parse_rate("1,500.5"), Decimal("1500.5000"))
        with self.assertRaises(ValueError):
            services.parse_rate("-1")
        with self.assertRaises(ValueError):
            services.parse_rate("")
        with self.assertRaises(ValueError):
            services.parse_rate("abc")

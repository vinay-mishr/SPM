import json
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.items.models import Item
from apps.parties.models import Party

from . import calc, services
from .models import InvNo, QuotationHeader, QuotationMeta, QuotationSubmission

TODAY = date.today().isoformat()

QUOT_DAT_DDL = """
CREATE TABLE quot_dat (
    quot_no varchar(6), quot_dt date, p_code varchar(4), i_code varchar(4), qty decimal(10,3),
    rate decimal(10,2), amount decimal(12,2), remk varchar(30), av varchar(2), dis decimal(5,2),
    vat decimal(5,2), vat_amt decimal(10,2), uname varchar(10), dis_amt decimal(10,2), party varchar(50),
    unit varchar(3), particular text, cur varchar(3), yn varchar(1), type varchar(1)
)
"""


class CalcTests(TestCase):
    def test_percentage_discount_and_gst(self):
        r = calc.calc_line(Decimal("2"), Decimal("1000"), Decimal("10"), 0, Decimal("18"), True)
        self.assertEqual(r["gross"], Decimal("2000.00"))
        self.assertEqual(r["discount"], Decimal("200.00"))
        self.assertEqual(r["taxable"], Decimal("1800.00"))
        self.assertEqual(r["gst"], Decimal("324.00"))
        self.assertEqual(r["total"], Decimal("2124.00"))

    def test_discount_amount_derives_percentage(self):
        r = calc.calc_line(Decimal("3"), Decimal("100"), 0, Decimal("50"), Decimal("18"), True)
        self.assertEqual(r["discount"], Decimal("50.00"))
        self.assertEqual(r["disc_pct"], Decimal("16.67"))
        self.assertEqual(r["gst"], Decimal("45.00"))

    def test_gst_off_gives_zero_gst(self):
        r = calc.calc_line(Decimal("1"), Decimal("584000"), 0, 0, Decimal("18"), False)
        self.assertEqual(r["gst"], Decimal("0"))
        self.assertEqual(r["total"], Decimal("584000.00"))

    def test_rounding_is_half_up(self):
        r = calc.calc_line(Decimal("1"), Decimal("0.05"), 0, 0, Decimal("10"), True)
        self.assertEqual(r["gst"], Decimal("0.01"))  # 0.005 -> 0.01
        r = calc.calc_line(Decimal("0.125"), Decimal("0.10"), 0, 0, 0, True)
        self.assertEqual(r["gross"], Decimal("0.01"))  # 0.0125 -> 0.01

    def test_totals_match_legacy_quotation_13(self):
        lines = [calc.calc_line(1, Decimal("580000"), 0, 0, 18, True), calc.calc_line(1, Decimal("4000"), 0, 0, 18, True)]
        t = calc.calc_totals(lines)
        self.assertEqual((t["total"], t["discount"], t["gst"], t["net"]),
                         (Decimal("584000.00"), Decimal("0.00"), Decimal("105120.00"), Decimal("689120.00")))

    def test_rejects_non_numbers(self):
        with self.assertRaises(calc.CalcError):
            calc.to_decimal("abc", "Rate")
        with self.assertRaises(calc.CalcError):
            calc.to_decimal("NaN", "Rate")


class QuotationTablesMixin:
    """quot_mst / quot_dat / inv_no / item / cust_mst and the new web_quot_audit / web_quot_submit
    all live in SQL Server (unmanaged); the tests create them on the in-memory database."""

    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            for model in (Party, Item, QuotationHeader, InvNo, QuotationMeta, QuotationSubmission):
                editor.create_model(model)
        with connection.cursor() as cur:
            cur.execute(QUOT_DAT_DDL)
            cur.execute("ALTER TABLE item ADD COLUMN cur_stk decimal(9,2)")
            cur.execute("ALTER TABLE cust_mst ADD COLUMN cst decimal(5,2)")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.cursor() as cur:
            cur.execute("DROP TABLE quot_dat")
        with connection.schema_editor() as editor:
            for model in (Party, Item, QuotationHeader, InvNo, QuotationMeta, QuotationSubmission):
                editor.delete_model(model)


class QuotationModuleTests(QuotationTablesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser(username="boss", password="S3cure-pass!", email="b@example.com")
        cls.viewer = User.objects.create_user(username="viewer", password="S3cure-pass!")
        cls.viewer.user_permissions.add(Permission.objects.get(codename="view_quotationheader"))
        cls.nobody = User.objects.create_user(username="nobody", password="S3cure-pass!")

    def setUp(self):
        Party.objects.create(party_code="S089", name="SHRI TEJA INDUSTRIES", city="JAIPUR", phone_1="9929748382",
                             address_1="KHASRA NO. 639, DABRI RAMPURA", address_2="JAIPUR, RAJASTHAN,", address_3="",
                             gst_no="08ANPPN9407J1ZC")
        Party.objects.create(party_code="E003", name="ELEENA COSMATICS", city="BADDI", phone_1="9815590032")
        Item.objects.create(item_code="0005", item_name_1="FLOW WRAP MACHINE MANUAL", unit="NUM", gst_percent=Decimal("18"),
                            hsn_code="84224000")
        Item.objects.create(item_code="0003", item_name_1="CHANGE PARTS", unit="NUM", gst_percent=Decimal("18"))
        Item.objects.create(item_code="0058", item_name_1="PACKING WOODEN CASE", unit="NUM", gst_percent=Decimal("0"))
        with connection.cursor() as cur:
            cur.execute("UPDATE cust_mst SET cst = 18 WHERE ccode = 'S089'")
            cur.execute("UPDATE item SET cur_stk = 5 WHERE i_code = '0005'")
            cur.execute("UPDATE item SET cur_stk = 1 WHERE i_code = '0003'")
        InvNo.objects.create(quot_no=Decimal("17"))
        # A quotation of the other legacy screen (type 'Q') -- must never show up or be touched here.
        QuotationHeader.objects.create(quot_no="17", quot_type="Q", quot_date=date.today(), party_code="E003",
                                       party_name="ELEENA COSMATICS", gst_applicable="Y", amount=Decimal("100"))
        self.client.force_login(self.admin)

    # --- helpers -----------------------------------------------------------------------
    def payload(self, **overrides):
        data = {
            "quot_no": "18", "quot_date": TODAY, "ref_no": "R-1", "ref_date": "26/06/2026",
            "gst_applicable": "Y", "party_code": "S089", "city": "JAIPUR", "phone": "9929748382",
            "kind_attention": ["SANTOSH KUMAR", "M-9929748382", ""], "remarks": "Price ex-works.",
            "terms": services.default_terms(), "bank": services.default_bank_lines(),
            "items": [
                {"item_code": "0005", "currency": "RS.", "qty": "1", "rate": "580000", "disc_pct": "0",
                 "disc_amt": "0", "gst_pct": "18", "particular": "Machine Model : SP FLOW WRAP 100S\nServo"},
                {"item_code": "0003", "currency": "RS.", "qty": "2", "rate": "2000", "disc_pct": "10",
                 "disc_amt": "0", "gst_pct": "18", "particular": ""},
            ],
        }
        data.update(overrides)
        return data

    def save(self, quotation=None, key=None, action="save", token=None, user=None):
        if user:
            self.client.force_login(user)
        return self.client.post(
            reverse("quotations:api_save"),
            data=json.dumps({"token": token or services.new_token(), "action": action, "key": key,
                             "quotation": quotation if quotation is not None else self.payload()}),
            content_type="application/json",
        )

    def lines(self, quot_no):
        with connection.cursor() as cur:
            cur.execute("SELECT i_code, qty, rate, amount, dis, dis_amt, vat, vat_amt, av, cur, unit, yn, type, particular, uname "
                        "FROM quot_dat WHERE quot_no = %s", [quot_no])
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def counter(self):
        return int(InvNo.objects.get().quot_no)

    # --- access ------------------------------------------------------------------------
    def test_anonymous_is_redirected_to_login(self):
        self.client.logout()
        for url in (reverse("quotations:list"), reverse("quotations:add"), reverse("quotations:print", args=["18"])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn(reverse("accounts:login"), response["Location"])
        response = self.client.post(reverse("quotations:api_save"), data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 302)

    def test_permissions_are_enforced(self):
        self.client.force_login(self.nobody)
        self.assertEqual(self.client.get(reverse("quotations:list")).status_code, 403)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("quotations:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("quotations:add")).status_code, 403)
        response = self.save(user=self.viewer)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(QuotationHeader.objects.filter(quot_no="18").exists())
        self.assertEqual(self.client.post(reverse("quotations:delete", args=["17"])).status_code, 403)

    def test_writes_switched_off(self):
        with mock.patch.object(services, "writes_enabled", return_value=False):
            response = self.save()
        self.assertEqual(response.status_code, 403)
        self.assertFalse(QuotationHeader.objects.filter(quot_no="18").exists())

    def test_sidebar_and_list_page(self):
        response = self.client.get(reverse("quotations:list"))
        self.assertContains(response, reverse("quotations:list"))
        for label in ("Add", "Modify", "Delete", "View", "Print", "Refresh", "Exit"):
            self.assertContains(response, f">{label}<")

    # --- add / reopen ------------------------------------------------------------------
    def test_add_page_offers_next_number_and_defaults(self):
        response = self.client.get(reverse("quotations:add"))
        self.assertEqual(response.status_code, 200)
        config = response.context["form_config"]
        self.assertEqual(config["quotation"]["quot_no"], "18")
        self.assertEqual(config["quotation"]["terms"][0], "1. 50% amount paid in advance and balance before receiving the material.")
        self.assertEqual(config["quotation"]["bank"], ["BANK NAME : HDFC BANK", "A/C NO : 50200066791400",
                                                       "IFSC CODE : HDFC0001307", "BRANCH : MOHALI"])
        self.assertTrue(config["token"])

    def test_create_with_multiple_items(self):
        response = self.save()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["quot_no"], "18")
        self.assertNotEqual(body["next_token"], "")

        h = QuotationHeader.objects.get(quot_no="18")
        self.assertEqual(h.quot_type, " ")
        self.assertEqual(h.div, "SP")
        self.assertEqual(h.party_name, "SHRI TEJA INDUSTRIES")
        self.assertEqual(h.party_code, "S089")
        self.assertEqual(h.gst_applicable, "Y")
        self.assertEqual(h.amount, Decimal("584000.00"))          # 580000 + 2 x 2000
        self.assertEqual(h.discount_amount, Decimal("400.00"))    # 10% of 4000
        self.assertEqual(h.gst_amount, Decimal("105048.00"))      # 18% of 580000 + 18% of 3600
        self.assertEqual(h.net_amount, Decimal("688648.00"))
        self.assertEqual(h.party_tax_rate, Decimal("18"))         # cust_mst.cst, like the legacy form
        self.assertEqual(h.ref_date, date(2026, 6, 26))
        self.assertEqual(h.term_1, "1. 50% amount paid in advance and balance before receiving the material.")
        self.assertEqual(h.bank_2, "A/C NO : 50200066791400")
        self.assertEqual(h.uname, "boss")
        self.assertEqual(self.counter(), 18)

        lines = self.lines("18")
        self.assertEqual(len(lines), 2)
        first, second = lines
        self.assertEqual((first["i_code"], first["cur"], first["unit"], first["yn"], first["type"]), ("0005", "RS.", "NUM", "Y", " "))
        self.assertEqual(Decimal(str(first["vat_amt"])), Decimal("104400.00"))
        self.assertEqual(first["av"], "A")        # 5 in stock >= 1
        self.assertEqual(second["av"], "PA")      # 1 in stock < 2
        self.assertEqual(Decimal(str(second["dis_amt"])), Decimal("400.00"))
        self.assertEqual(Decimal(str(second["amount"])), Decimal("4000.00"))   # gross, as in legacy
        self.assertIn("SP FLOW WRAP 100S", first["particular"])

        meta = QuotationMeta.objects.get(quot_no="18")
        self.assertEqual(meta.created_by, "boss")
        self.assertIsNone(meta.confirmed_at)

    def test_reopen_returns_saved_items(self):
        self.save()
        data = services.get_quotation("18")
        self.assertEqual([l["item_code"] for l in data["items"]], ["0005", "0003"])
        self.assertEqual(data["items"][1]["disc_pct"], "10.00")
        self.assertEqual(data["items"][1]["disc_amt"], "400.00")
        self.assertEqual(data["net_amount"], "688648.00")
        self.assertEqual(data["kind_attention"], ["SANTOSH KUMAR", "M-9929748382", ""])
        response = self.client.get(reverse("quotations:edit", args=["18"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form_config"]["quotation"]["items"][0]["item_name"], "FLOW WRAP MACHINE MANUAL")

    def test_discount_amount_round_trips(self):
        items = [{"item_code": "0005", "currency": "USD", "qty": "3", "rate": "100", "disc_pct": "0",
                  "disc_amt": "50", "gst_pct": "0", "particular": ""}]
        self.assertEqual(self.save(self.payload(items=items, gst_applicable="N")).status_code, 200)
        line = services.get_quotation("18")["items"][0]
        self.assertEqual((line["disc_pct"], line["disc_amt"], line["disc_pct_effective"]), ("0.00", "50.00", "16.67"))
        self.assertEqual(QuotationHeader.objects.get(quot_no="18").net_amount, Decimal("250.00"))

    def test_gst_disabled_means_zero_gst(self):
        self.assertEqual(self.save(self.payload(gst_applicable="N")).status_code, 200)
        h = QuotationHeader.objects.get(quot_no="18")
        self.assertEqual(h.gst_amount, Decimal("0.00"))
        self.assertEqual(h.net_amount, Decimal("583600.00"))
        self.assertTrue(all(Decimal(str(l["vat_amt"])) == 0 for l in self.lines("18")))
        self.assertEqual(Decimal(str(self.lines("18")[0]["vat"])), Decimal("18"))  # rate kept, like legacy

    def test_client_totals_are_ignored(self):
        payload = self.payload(net_amount="1.00", total_amount="1.00")
        payload["items"][0]["amount"] = "1"
        self.save(payload)
        self.assertEqual(QuotationHeader.objects.get(quot_no="18").net_amount, Decimal("688648.00"))

    # --- modify -------------------------------------------------------------------------
    def test_modify_replaces_lines_instead_of_duplicating(self):
        self.save()
        items = [{"item_code": "0058", "currency": "RS.", "qty": "1", "rate": "550", "disc_pct": "0",
                  "disc_amt": "0", "gst_pct": "0", "particular": "Packing"}]
        response = self.save(self.payload(items=items, subject="Revised"), key="18")
        self.assertEqual(response.status_code, 200, response.content)
        lines = self.lines("18")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["i_code"], "0058")
        self.assertEqual(lines[0]["av"], "NA")  # no stock
        h = QuotationHeader.objects.get(quot_no="18")
        self.assertEqual((h.subject, h.amount, h.net_amount), ("Revised", Decimal("550.00"), Decimal("550.00")))
        self.assertEqual(self.counter(), 18)
        self.assertEqual(QuotationMeta.objects.get(quot_no="18").updated_by, "boss")

    def test_modify_keeps_subject_and_title_the_screen_no_longer_shows(self):
        QuotationHeader.objects.create(quot_no="20", quot_type=" ", quot_date=date.today(), party_code="S089",
                                       subject="Old subject", description="Old title")
        response = self.save(self.payload(quot_no="20"), key="20")
        self.assertEqual(response.status_code, 200, response.content)
        h = QuotationHeader.objects.get(quot_no="20")
        self.assertEqual((h.subject, h.description), ("Old subject", "Old title"))
        self.assertEqual(len(self.lines("20")), 2)

    def test_entry_screen_has_no_subject_or_title_inputs(self):
        response = self.client.get(reverse("quotations:add"))
        self.assertNotContains(response, 'data-f="subject"')
        self.assertNotContains(response, 'data-f="description"')

    def test_modify_cannot_change_number_or_touch_type_q(self):
        self.save()
        response = self.save(self.payload(quot_no="19"), key="18")
        self.assertEqual(response.status_code, 400)
        response = self.save(self.payload(quot_no="17"), key="17")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(QuotationHeader.objects.get(quot_no="17").party_code, "E003")
        self.assertEqual(self.client.get(reverse("quotations:edit", args=["17"])).status_code, 404)

    def test_modify_missing_quotation(self):
        response = self.save(self.payload(quot_no="55"), key="55")
        self.assertEqual(response.status_code, 404)

    # --- view ---------------------------------------------------------------------------
    def test_view_is_read_only(self):
        self.save()
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("quotations:view", args=["18"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is-readonly")
        self.assertEqual(response.context["form_config"]["mode"], "view")
        self.assertFalse(response.context["form_config"]["can_confirm"])

    # --- listing -----------------------------------------------------------------------
    def test_list_filters_searches_and_excludes_type_q(self):
        self.save()
        self.save(self.payload(quot_no="19", party_code="E003", quot_date="2026-01-05", description="", subject="Spare parts"))
        url = reverse("quotations:list")
        rows = self.client.get(url).context["rows"]
        self.assertEqual([r["quot_no"] for r in rows], ["18"])  # today only; 17 is type Q
        rows = self.client.get(url, {"start_date": "01/01/2026", "end_date": "31/12/2099"}).context["rows"]
        self.assertEqual([r["quot_no"] for r in rows], ["18", "19"])  # newest first
        self.assertEqual(rows[0]["description"], "FLOW WRAP MACHINE MANUAL (+1 more)")  # no title: first item
        self.assertEqual(rows[1]["description"], "Spare parts")  # an older quotation's subject still shows
        rows = self.client.get(url, {"start_date": "01/01/2026", "end_date": "31/12/2099", "q": "eleena"}).context["rows"]
        self.assertEqual([r["quot_no"] for r in rows], ["19"])
        rows = self.client.get(url, {"start_date": "01/01/2026", "end_date": "31/12/2099", "q": "18"}).context["rows"]
        self.assertEqual([r["quot_no"] for r in rows], ["18"])
        response = self.client.get(url, {"start_date": "31/12/2026", "end_date": "01/01/2026"})
        self.assertContains(response, "Start Date cannot be later than End Date.")

    def test_list_pagination(self):
        for n in range(30, 30 + services.PAGE_SIZE + 3):
            QuotationHeader.objects.create(quot_no=str(n), quot_type=" ", quot_date=date.today(), party_name="P")
        response = self.client.get(reverse("quotations:list"))
        self.assertEqual(len(response.context["rows"]), services.PAGE_SIZE)
        self.assertEqual(response.context["rows"][0]["quot_no"], str(29 + services.PAGE_SIZE + 3))
        response = self.client.get(reverse("quotations:list"), {"page": 2})
        self.assertEqual(len(response.context["rows"]), 3)

    # --- print -------------------------------------------------------------------------
    def test_print_shows_saved_totals(self):
        self.save()
        response = self.client.get(reverse("quotations:print", args=["18"]))
        self.assertEqual(response.status_code, 200)
        for text in ("584000.00", "400.00", "105048.00", "688648.00", "SHRI TEJA INDUSTRIES", "Authorised Signatory",
                     "BANK NAME : HDFC BANK", "Kind Attn.", "SP FLOW WRAP 100S", "84224000",
                     "KHASRA NO. 639, DABRI RAMPURA", "JAIPUR, RAJASTHAN,", "08ANPPN9407J1ZC"):
            self.assertContains(response, text)
        data = services.get_quotation("18")
        # Customer Master address in the legacy report's order (cadd1, cadd2, cadd4, cadd3), blanks skipped.
        self.assertEqual(data["party_address"], ["KHASRA NO. 639, DABRI RAMPURA", "JAIPUR, RAJASTHAN,", "JAIPUR"])
        self.assertEqual(data["party_gstin"], "08ANPPN9407J1ZC")
        self.assertEqual(self.client.get(reverse("quotations:print", args=["17"])).status_code, 404)

    def test_pdf_download(self):
        self.save()
        response = self.client.get(reverse("quotations:pdf", args=["18"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    # --- confirm -----------------------------------------------------------------------
    def test_confirm_saves_and_records_who_confirmed(self):
        response = self.save(action="confirm")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Quotation 18 confirmed.")
        meta = QuotationMeta.objects.get(quot_no="18")
        self.assertEqual(meta.confirmed_by, "boss")
        self.assertEqual(services.get_quotation("18")["confirmed_by"], "boss")
        self.assertIsNotNone(meta.confirmed_at)
        self.assertTrue(self.client.get(reverse("quotations:list")).context["rows"][0]["confirmed"])
        self.assertTrue(services.get_quotation("18")["confirmed"])

    # --- delete ------------------------------------------------------------------------
    def test_delete_last_number_decrements_counter(self):
        self.save()
        self.assertEqual(self.counter(), 18)
        self.assertEqual(self.client.get(reverse("quotations:delete", args=["18"])).status_code, 405)
        response = self.client.post(reverse("quotations:delete", args=["18"]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuotationHeader.objects.filter(quot_no="18").exists())
        self.assertEqual(self.lines("18"), [])
        self.assertEqual(self.counter(), 17)
        self.assertFalse(QuotationMeta.objects.filter(quot_no="18").exists())

    def test_delete_older_number_keeps_counter(self):
        self.save()
        self.save(self.payload(quot_no="19"))
        self.client.post(reverse("quotations:delete", args=["18"]))
        self.assertEqual(self.counter(), 19)
        self.assertTrue(QuotationHeader.objects.filter(quot_no="19").exists())
        self.assertEqual(len(self.lines("19")), 2)

    def test_delete_refuses_type_q(self):
        response = self.client.post(reverse("quotations:delete", args=["17"]), follow=True)
        self.assertContains(response, "can&#x27;t be deleted here")
        self.assertTrue(QuotationHeader.objects.filter(quot_no="17").exists())

    # --- duplicates / idempotency -------------------------------------------------------
    def test_duplicate_number_rejected_including_type_q_numbers(self):
        response = self.save(self.payload(quot_no="17"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.json()["message"])
        self.save()
        response = self.save(self.payload())
        self.assertEqual(response.status_code, 400)
        self.assertIn("next free number is 19", response.json()["message"])
        self.assertEqual(len(self.lines("18")), 2)

    def test_repeated_submit_with_same_token_saves_once(self):
        token = services.new_token()
        first = self.save(token=token)
        second = self.save(token=token)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["replayed"])
        self.assertEqual(QuotationHeader.objects.filter(quot_no="18").count(), 1)
        self.assertEqual(len(self.lines("18")), 2)
        self.assertEqual(QuotationSubmission.objects.filter(token=token).count(), 1)

    def test_failed_submit_can_be_retried_with_same_token(self):
        token = services.new_token()
        bad = self.save(self.payload(items=[]), token=token)
        self.assertEqual(bad.status_code, 400)
        good = self.save(token=token)
        self.assertEqual(good.status_code, 200)
        self.assertFalse(good.json().get("replayed", False))

    def test_missing_or_bad_token_rejected(self):
        response = self.client.post(reverse("quotations:api_save"), data=json.dumps({"quotation": self.payload()}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(QuotationHeader.objects.filter(quot_no="18").exists())

    # --- validation ---------------------------------------------------------------------
    def test_empty_item_list_rejected(self):
        response = self.save(self.payload(items=[]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("items", response.json()["errors"])
        self.assertFalse(QuotationHeader.objects.filter(quot_no="18").exists())
        self.assertEqual(self.counter(), 17)

    def test_invalid_inputs_rejected(self):
        line = self.payload()["items"][0]
        cases = [
            ({"quot_no": "1A"}, "quot_no"),
            ({"quot_no": "1234567"}, "quot_no"),
            ({"quot_date": "31/02/2026"}, "quot_date"),
            ({"quot_date": ""}, "quot_date"),
            ({"ref_date": "nope"}, "ref_date"),
            ({"party_code": ""}, "party_code"),
            ({"party_code": "ZZZZ"}, "party_code"),
            ({"gst_applicable": "X"}, "gst_applicable"),
            ({"city": "X" * 31}, "city"),
            ({"terms": ["X" * 81]}, "terms"),
            ({"items": [{**line, "item_code": "9999"}]}, "items"),
            ({"items": [{**line, "qty": "0"}]}, "items"),
            ({"items": [{**line, "qty": "-1"}]}, "items"),
            ({"items": [{**line, "qty": "1.0001"}]}, "items"),
            ({"items": [{**line, "rate": "-5"}]}, "items"),
            ({"items": [{**line, "rate": "abc"}]}, "items"),
            ({"items": [{**line, "disc_pct": "101"}]}, "items"),
            ({"items": [{**line, "disc_amt": "600000"}]}, "items"),
            ({"items": [{**line, "gst_pct": "150"}]}, "items"),
            ({"items": [{**line, "currency": "RUPEES"}]}, "items"),
            ({"items": ["junk"]}, "items"),
        ]
        for overrides, key in cases:
            with self.subTest(overrides=overrides):
                response = self.save(self.payload(**overrides))
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(key, response.json()["errors"])
        self.assertFalse(QuotationHeader.objects.filter(quot_no="18").exists())
        self.assertEqual(self.lines("18"), [])

    def test_gst_total_over_legacy_column_limit_rejected(self):
        items = [{"item_code": "0005", "currency": "RS.", "qty": "1", "rate": "9000000", "disc_pct": "0",
                  "disc_amt": "0", "gst_pct": "18", "particular": ""}]
        response = self.save(self.payload(items=items))
        self.assertEqual(response.status_code, 400)
        self.assertIn("GST amount", response.json()["message"])

    def test_malformed_json(self):
        response = self.client.post(reverse("quotations:api_save"), data="{not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    # --- lookups ----------------------------------------------------------------------
    def test_party_and_item_lookups(self):
        parties = self.client.get(reverse("quotations:api_parties"), {"q": "teja"}).json()["parties"]
        self.assertEqual(parties, [{"code": "S089", "name": "SHRI TEJA INDUSTRIES", "city": "JAIPUR", "phone": "9929748382"}])
        items = self.client.get(reverse("quotations:api_items"), {"q": "wooden"}).json()["items"]
        self.assertEqual(items[0]["code"], "0058")
        self.assertEqual(items[0]["gst_percent"], "0.00")


class CreateTablesCommandTests(TestCase):
    def test_default_run_only_prints_the_sql(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with mock.patch("django.db.backends.utils.CursorWrapper.execute") as execute:
            call_command("create_quotation_tables", stdout=out)
        execute.assert_not_called()
        text = out.getvalue()
        self.assertIn("CREATE TABLE dbo.web_quot_audit", text)
        self.assertIn("CREATE TABLE dbo.web_quot_submit", text)
        self.assertNotIn("DROP", text.upper())
        self.assertNotIn("ALTER", text.upper())
        self.assertIn("Nothing was run", text)

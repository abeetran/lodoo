from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


def _order_payload(**overrides):
    payload = {
        "code": "DH2026070001",
        "school": {"name": "Trường Mầm non Hoa Sen"},
        "products": [
            {"code": "TP-THIT-001", "name": "Thịt heo tươi"},
            {"code": "TP-RAU-001", "name": "Rau muống", "quantity": 3},
        ],
    }
    payload.update(overrides)
    return payload


class TestOrderFetch(TransactionCase):
    def _food(self, code, source="foods"):
        return self.env["product.template"].create(
            {
                "name": "Thực phẩm %s" % code,
                "default_code": code,
                "crall_food_source": source,
            }
        )

    def _school(self, name="Trường Mầm non Hoa Sen"):
        return self.env["res.partner"].create(
            {"name": name, "school_code": "5", "is_company": True}
        )

    def test_fetch_creates_orders(self):
        self._food("TP-THIT-001")
        self._food("TP-RAU-001")
        school = self._school()
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "message": "Danh sách đơn hàng",
                "data": [_order_payload()],
                "pagination": {"total": 1},
            }
            counts = self.env["sale.order"].fetch_supplier_orders(
                page=1, per_page=20, status="DANG_GIAO"
            )
        mock_client.return_value.fetch_supplier_orders.assert_called_once_with(
            {"page": 1, "per_page": 20, "status": "DANG_GIAO"}
        )
        self.assertEqual(
            (counts["created"], counts["updated"], counts["fetched"]),
            (1, 0, 1),
        )
        order = self.env["sale.order"].search(
            [("catering_reference", "=", "DH2026070001")], limit=1
        )
        self.assertEqual(order.name, "DH2026070001")
        self.assertEqual(order.partner_id, school)
        self.assertEqual(order.date_order.date(), date.today())
        self.assertEqual(order.commitment_date.date(), date.today())
        lines = order.order_line.sorted("product_uom_qty")
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            [line.product_uom_qty for line in lines], [1.0, 3.0]
        )
        self.assertEqual(
            lines.mapped("product_id.default_code"),
            ["TP-THIT-001", "TP-RAU-001"],
        )
        self.assertEqual(counts["lines_ok"], 2)
        self.assertEqual(counts["lines_skipped"], 0)

    def test_fetch_creates_partner_when_unknown(self):
        self._food("TP-THIT-001")
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [_order_payload()],
                "pagination": {"total": 1},
            }
            counts = self.env["sale.order"].fetch_supplier_orders()
        self.assertEqual(counts["partners_created"], 1)
        partner = self.env["res.partner"].search(
            [("name", "=", "Trường Mầm non Hoa Sen")], limit=1
        )
        self.assertTrue(partner.is_company)
        self.assertEqual(partner.customer_rank, 1)

    def test_fetch_skips_unknown_products(self):
        self._food("TP-THIT-001")
        self._school()
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [
                    _order_payload(
                        products=[
                            {"code": "TP-THIT-001"},
                            {"code": "TP-KHONG-CO"},
                            {"name": "Thiếu mã"},
                        ]
                    )
                ],
                "pagination": {"total": 1},
            }
            counts = self.env["sale.order"].fetch_supplier_orders()
        self.assertEqual(
            (counts["lines_ok"], counts["lines_skipped"]), (1, 2)
        )
        order = self.env["sale.order"].search(
            [("catering_reference", "=", "DH2026070001")], limit=1
        )
        self.assertEqual(len(order.order_line), 1)

    def test_fetch_prefers_foods_source(self):
        self._food("TP-DUP-001", source="standard")
        foods = self._food("TP-DUP-001", source="foods")
        self._school()
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [_order_payload(products=[{"code": "TP-DUP-001"}])],
                "pagination": {"total": 1},
            }
            self.env["sale.order"].fetch_supplier_orders()
        order = self.env["sale.order"].search(
            [("catering_reference", "=", "DH2026070001")], limit=1
        )
        self.assertEqual(
            order.order_line.product_id.product_tmpl_id, foods
        )

    def test_fetch_skips_manual_orders(self):
        self._food("TP-THIT-001")
        self._food("TP-RAU-001")
        school = self._school()
        draft = self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-DRAFT",
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.env["product.product"]
                            .search([], limit=1)
                            .id,
                            "product_uom_qty": 9,
                        },
                    )
                ],
            }
        )
        locked = self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-LOCKED",
            }
        )
        locked.write({"catering_state": "in_production"})
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [
                    _order_payload(
                        code="DH-DRAFT",
                        products=[{"code": "TP-RAU-001"}],
                    ),
                    _order_payload(code="DH-LOCKED"),
                ],
                "pagination": {"total": 2},
            }
            counts = self.env["sale.order"].fetch_supplier_orders()
        self.assertEqual(
            (counts["updated"], counts["skipped_manual"]), (0, 2)
        )
        self.assertEqual(len(draft.order_line), 1)
        self.assertEqual(draft.order_line.product_uom_qty, 9)
        self.assertEqual(len(locked.order_line), 0)

    def test_fetch_updates_locked_hnck_order(self):
        self._food("TP-THIT-001")
        self._food("TP-RAU-001")
        self._school()
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [
                    _order_payload(
                        code="DH-HNCK-001",
                        products=[{"code": "TP-THIT-001"}],
                    )
                ],
                "pagination": {"total": 1},
            }
            self.env["sale.order"].fetch_supplier_orders()
        order = self.env["sale.order"].search(
            [("catering_reference", "=", "DH-HNCK-001")], limit=1
        )
        self.assertTrue(order.hnck_order)
        order.write({"catering_state": "in_production"})
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [
                    _order_payload(
                        code="DH-HNCK-001",
                        status="DANG_GIAO",
                        products=[{"code": "TP-RAU-001"}],
                    )
                ],
                "pagination": {"total": 1},
            }
            counts = self.env["sale.order"].fetch_supplier_orders()
        self.assertEqual((counts["updated"], counts["skipped_manual"]), (1, 0))
        self.assertEqual(order.catering_state, "dispatched")
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(
            order.order_line.product_id.default_code, "TP-RAU-001"
        )

    def test_hnck_order_direct_write_blocked(self):
        school = self._school()
        other = self.env["res.partner"].create({"name": "Trường khác"})
        hnck = self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-HNCK-002",
                "hnck_order": True,
            }
        )
        manual = self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-MANUAL-002",
            }
        )
        with self.assertRaises(UserError):
            hnck.write({"partner_id": other.id})
        hnck.write({"catering_state": "confirmed"})
        self.assertEqual(hnck.catering_state, "confirmed")
        hnck.with_context(hnck_sync=True).write({"partner_id": other.id})
        self.assertEqual(hnck.partner_id, other)
        manual.write({"partner_id": other.id})
        self.assertEqual(manual.partner_id, other)

    def test_hnck_line_guards(self):
        school = self._school()
        product = self.env["product.product"].search([], limit=1)
        hnck = (
            self.env["sale.order"]
            .with_context(hnck_sync=True)
            .create(
                {
                    "partner_id": school.id,
                    "catering_reference": "DH-HNCK-003",
                    "hnck_order": True,
                    "order_line": [
                        (
                            0,
                            0,
                            {"product_id": product.id, "product_uom_qty": 2},
                        )
                    ],
                }
            )
        )
        line = hnck.order_line
        with self.assertRaises(UserError):
            line.write({"product_uom_qty": 5})
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            self.env["sale.order.line"].create(
                {
                    "order_id": hnck.id,
                    "product_id": product.id,
                    "product_uom_qty": 1,
                }
            )
        line.with_context(hnck_sync=True).write({"product_uom_qty": 5})
        self.assertEqual(line.product_uom_qty, 5)

    def test_wizard_reports_skipped_manual(self):
        school = self._school()
        self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-MANUAL-004",
            }
        )
        wizard = self.env["set_top_menu.order.fetch.wizard"].create({})
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [_order_payload(code="DH-MANUAL-004")],
                "pagination": {"total": 1},
            }
            wizard.action_confirm_fetch()
        self.assertIn("Bỏ qua (đơn nhập tay): 1", wizard.result_text)

    def test_fetch_rejects_failure(self):
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": False,
                "message": "Hết hạn",
            }
            with self.assertRaises(UserError):
                self.env["sale.order"].fetch_supplier_orders()
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": {"code": "DH-NOT-A-LIST"},
            }
            with self.assertRaises(UserError):
                self.env["sale.order"].fetch_supplier_orders()

    def test_state_labels_renamed(self):
        selection = dict(
            self.env["sale.order"]._fields["catering_state"].selection
        )
        self.assertEqual(selection["draft"], "Chờ xác nhận")
        self.assertEqual(selection["in_production"], "Đang chuẩn bị")

    def test_fetch_maps_api_status_on_create(self):
        self._school()
        cases = [
            ("CHO_XAC_NHAN", "draft"),
            ("TU_CHOI", "cancelled"),
            ("DANG_CHUAN_BI", "in_production"),
            ("DANG_GIAO", "dispatched"),
            ("DA_GIAO", "delivered"),
            ("GIAO_HANG_THANH_CONG", "delivered"),
            ("HUY", "cancelled"),
        ]
        payloads = [
            _order_payload(code="DH-MAP-%02d" % index, status=status)
            for index, (status, _expected) in enumerate(cases)
        ]
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": payloads,
                "pagination": {"total": len(payloads)},
            }
            self.env["sale.order"].fetch_supplier_orders()
        for index, (_status, expected) in enumerate(cases):
            order = self.env["sale.order"].search(
                [("catering_reference", "=", "DH-MAP-%02d" % index)],
                limit=1,
            )
            self.assertEqual(order.catering_state, expected)

    def test_fetch_tra_hang_and_unknown_leave_state(self):
        self._school()
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [
                    _order_payload(code="DH-TRA-001", status="TRA_HANG"),
                    _order_payload(code="DH-UNK-001", status="XYZ"),
                    _order_payload(code="DH-NOSTATUS-001"),
                ],
                "pagination": {"total": 3},
            }
            self.env["sale.order"].fetch_supplier_orders()
        for code in ("DH-TRA-001", "DH-UNK-001", "DH-NOSTATUS-001"):
            order = self.env["sale.order"].search(
                [("catering_reference", "=", code)], limit=1
            )
            self.assertEqual(order.catering_state, "draft")
        kept = self.env["sale.order"].search(
            [("catering_reference", "=", "DH-TRA-001")], limit=1
        )
        kept.write({"catering_state": "confirmed"})
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [_order_payload(code="DH-TRA-001", status="TRA_HANG")],
                "pagination": {"total": 1},
            }
            self.env["sale.order"].fetch_supplier_orders()
        self.assertEqual(kept.catering_state, "confirmed")

    def test_wizard_confirm_passes_params(self):
        self._food("TP-THIT-001")
        self._school()
        wizard = self.env["set_top_menu.order.fetch.wizard"].create(
            {
                "page": 2,
                "status": "DA_GIAO",
                "order_date_from": date(2026, 9, 1),
                "order_date_to": date(2026, 9, 30),
            }
        )
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [_order_payload()],
                "pagination": {"total": 1},
            }
            result = wizard.action_confirm_fetch()
        mock_client.return_value.fetch_supplier_orders.assert_called_once_with(
            {
                "page": 2,
                "per_page": 20,
                "status": "DA_GIAO",
                "order_date_from": "2026-09-01",
                "order_date_to": "2026-09-30",
            }
        )
        self.assertEqual(wizard.state, "done")
        self.assertIn("Tạo mới: 1", wizard.result_text)
        self.assertEqual(result["res_id"], wizard.id)
        self.assertEqual(result["target"], "new")

    def test_wizard_confirm_passes_code_and_school(self):
        self._food("TP-THIT-001")
        school = self._school()
        wizard = self.env["set_top_menu.order.fetch.wizard"].create(
            {
                "order_code": "DH2026070001",
                "school_id": school.id,
                "page": 1,
                "status": "DANG_GIAO",
            }
        )
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [_order_payload()],
                "pagination": {"total": 1},
            }
            wizard.action_confirm_fetch()
        mock_client.return_value.fetch_supplier_orders.assert_called_once_with(
            {
                "page": 1,
                "per_page": 20,
                "status": "DANG_GIAO",
                "code": "DH2026070001",
                "school_id": "5",
            }
        )
        self.assertEqual(wizard.state, "done")

    def test_wizard_omits_empty_code_and_school(self):
        self._food("TP-THIT-001")
        plain = self.env["res.partner"].create({"name": "Khách lẻ"})
        wizard = self.env["set_top_menu.order.fetch.wizard"].create(
            {
                "school_id": plain.id,
                "page": 1,
                "status": "DANG_GIAO",
            }
        )
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [],
                "pagination": {"total": 0},
            }
            wizard.action_confirm_fetch()
        params = (
            mock_client.return_value.fetch_supplier_orders.call_args[0][0]
        )
        self.assertNotIn("code", params)
        self.assertNotIn("school_id", params)

    def test_wizard_all_status_omits_status_param(self):
        self._food("TP-THIT-001")
        wizard = self.env["set_top_menu.order.fetch.wizard"].create(
            {"page": 1, "status": "ALL"}
        )
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [],
                "pagination": {"total": 0},
            }
            wizard.action_confirm_fetch()
        mock_client.return_value.fetch_supplier_orders.assert_called_once_with(
            {"page": 1, "per_page": 20}
        )
        self.assertEqual(wizard.state, "done")

    def test_wizard_empty_fields_omit_params(self):
        self._food("TP-THIT-001")
        wizard = self.env["set_top_menu.order.fetch.wizard"].create({})
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "data": [],
                "pagination": {"total": 0},
            }
            wizard.action_confirm_fetch()
        mock_client.return_value.fetch_supplier_orders.assert_called_once_with(
            {"per_page": 20}
        )
        self.assertEqual(wizard.state, "done")

    def test_reference_entered_on_create_kept(self):
        school = self._school()
        typed = self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-TAY-001",
            }
        )
        self.assertEqual(typed.catering_reference, "DH-TAY-001")
        sequenced = self.env["sale.order"].create(
            {"partner_id": school.id}
        )
        self.assertTrue(sequenced.catering_reference.startswith("ORD/"))

    def test_reference_change_blocked_on_write(self):
        school = self._school()
        order = self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-TAY-002",
            }
        )
        with self.assertRaises(UserError):
            order.write({"catering_reference": "DH-KHAC"})
        order.write({"catering_reference": "DH-TAY-002"})
        self.assertEqual(order.catering_reference, "DH-TAY-002")

    def test_line_create_defaults_name_and_uom_from_product(self):
        school = self._school()
        template = self._food("TP-THIT-001")
        order = self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-LINE-001",
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 2,
            }
        )
        self.assertIn("TP-THIT-001", line.name)
        self.assertEqual(line.product_uom, template.uom_id)
        named = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "name": "Tên giữ nguyên",
                "product_uom_qty": 1,
            }
        )
        self.assertEqual(named.name, "Tên giữ nguyên")
        self.assertEqual(named.product_uom, template.uom_id)

    def test_line_create_defaults_variant_from_template(self):
        school = self._school()
        template = self._food("TP-THIT-001")
        order = self.env["sale.order"].create(
            {
                "partner_id": school.id,
                "catering_reference": "DH-LINE-002",
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_template_id": template.id,
                "product_uom_qty": 1,
            }
        )
        self.assertEqual(line.product_id, template.product_variant_id)
        self.assertIn("TP-THIT-001", line.name)
        self.assertEqual(line.product_uom, template.uom_id)

    def test_wizard_defaults(self):
        fields = self.env["set_top_menu.order.fetch.wizard"]._fields
        wizard = self.env["set_top_menu.order.fetch.wizard"].new({})
        self.assertFalse(wizard.page)
        self.assertEqual(wizard.status, "ALL")
        self.assertNotIn("per_page", fields)
        self.assertNotIn("preview_text", fields)
        self.assertNotIn("x_nonce", fields)
        self.assertNotIn("x_timestamp", fields)
        self.assertEqual(len(fields["status"].selection), 9)
        self.assertEqual(fields["status"].selection[0][0], "ALL")

    def test_daily_tree_has_fetch_button(self):
        view = self.env.ref("set_top_menu.view_daily_order_tree")
        self.assertIn("action_open_fetch_wizard", view.arch_db)
        action_view = self.env.ref("set_top_menu.action_daily_orders_tree_view")
        self.assertEqual(action_view.view_id, view)

    def test_open_fetch_wizard(self):
        result = self.env["sale.order"].action_open_fetch_wizard()
        self.assertEqual(result["res_model"], "set_top_menu.order.fetch.wizard")
        self.assertEqual(result["target"], "new")

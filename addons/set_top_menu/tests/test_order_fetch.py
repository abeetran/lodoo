import time
from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.crall_material.models.hnck_client import HnckClient


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

    def test_fetch_updates_draft_skips_locked(self):
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
        self.assertEqual((counts["updated"], counts["skipped_locked"]), (1, 1))
        self.assertEqual(len(draft.order_line), 1)
        self.assertEqual(
            draft.order_line.product_id.default_code, "TP-RAU-001"
        )
        self.assertEqual(len(locked.order_line), 0)

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
            },
            x_nonce=wizard.x_nonce,
            x_timestamp=wizard.x_timestamp,
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
            },
            x_nonce=wizard.x_nonce,
            x_timestamp=wizard.x_timestamp,
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
        sign_kwargs = (
            mock_client.return_value.fetch_supplier_orders.call_args[1]
        )
        self.assertEqual(sign_kwargs["x_nonce"], wizard.x_nonce)
        self.assertEqual(sign_kwargs["x_timestamp"], wizard.x_timestamp)

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
            {"page": 1, "per_page": 20},
            x_nonce=wizard.x_nonce,
            x_timestamp=wizard.x_timestamp,
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
            {"per_page": 20},
            x_nonce=wizard.x_nonce,
            x_timestamp=wizard.x_timestamp,
        )
        self.assertEqual(wizard.state, "done")

    def _token_params(self, token="preview-token-abcdef"):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(
            "crall_material.hnck_api_base", "https://example.com/api/"
        )
        icp.set_param("crall_material.hnck_access_token", token)
        icp.set_param(
            "crall_material.hnck_token_expires_at",
            str(time.time() + 3600),
        )

    def test_preview_shows_request_details(self):
        self._token_params()
        school = self._school()
        wizard = self.env["set_top_menu.order.fetch.wizard"].create(
            {
                "order_code": "DH1",
                "school_id": school.id,
                "page": 2,
                "status": "DA_GIAO",
                "order_date_from": date(2026, 9, 1),
                "order_date_to": date(2026, 9, 30),
            }
        )
        preview = wizard.preview_text
        self.assertIn("Method: GET", preview)
        self.assertIn(
            "https://example.com/api/supplier/orders"
            "?per_page=20&page=2&status=DA_GIAO&code=DH1&school_id=5"
            "&order_date_from=2026-09-01&order_date_to=2026-09-30",
            preview,
        )
        self.assertIn("Authorization: Bearer previe...cdef", preview)
        self.assertNotIn("preview-token-abcdef", preview)
        self.assertIn("Accept: application/json", preview)

    def test_preview_without_token_notes_refresh(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "crall_material.hnck_api_base", "https://example.com/api/"
        )
        wizard = self.env["set_top_menu.order.fetch.wizard"].create(
            {"page": 1, "status": "ALL"}
        )
        preview = wizard.preview_text
        self.assertIn("Method: GET", preview)
        self.assertIn(
            "https://example.com/api/supplier/orders?per_page=20&page=1",
            preview,
        )
        self.assertIn("sẽ lấy token mới khi xác nhận", preview)

    def test_preview_shows_signature_headers(self):
        self._token_params()
        self.env["ir.config_parameter"].sudo().set_param(
            "crall_material.hnck_hmac_secret", "s3cret"
        )
        wizard = self.env["set_top_menu.order.fetch.wizard"].create(
            {
                "page": 1,
                "status": "ALL",
                "x_nonce": "fixed-nonce-001",
                "x_timestamp": "1790044905",
            }
        )
        expected = HnckClient(self.env).signature(
            "GET",
            "/api/supplier/orders",
            "1790044905",
            "fixed-nonce-001",
            b"",
        )
        preview = wizard.preview_text
        self.assertIn("X-Timestamp: 1790044905", preview)
        self.assertIn("X-Nonce: fixed-nonce-001", preview)
        self.assertIn("X-Signature: %s" % expected, preview)

    def test_wizard_defaults(self):
        fields = self.env["set_top_menu.order.fetch.wizard"]._fields
        wizard = self.env["set_top_menu.order.fetch.wizard"].new({})
        self.assertFalse(wizard.page)
        self.assertEqual(wizard.status, "ALL")
        self.assertNotIn("per_page", fields)
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

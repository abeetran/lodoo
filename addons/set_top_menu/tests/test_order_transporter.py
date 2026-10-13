from unittest.mock import patch

from odoo.tests.common import TransactionCase


def _order_payload(**overrides):
    payload = {
        "code": "DH-TRANS-001",
        "school": {"name": "Trường Mầm non Hoa Sen"},
        "products": [],
        "status": "DANG_GIAO",
        "transporter": {
            "name": "Nguyễn Văn A",
            "phone": "0900000001",
            "code": "NVGH-001",
        },
    }
    payload.update(overrides)
    return payload


class TestOrderTransporter(TransactionCase):
    def _fetch(self, payloads):
        client_path = "odoo.addons.set_top_menu.models.sale_order.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.fetch_supplier_orders.return_value = {
                "success": True,
                "message": "Danh sách đơn hàng",
                "data": payloads,
                "pagination": {"total": len(payloads)},
            }
            return self.env["sale.order"].fetch_supplier_orders(
                status="DANG_GIAO"
            )

    def _order(self, code):
        return self.env["sale.order"].search(
            [("catering_reference", "=", code)], limit=1
        )

    def test_fetch_saves_transporter_for_delivering(self):
        counts = self._fetch([_order_payload()])
        order = self._order("DH-TRANS-001")
        self.assertEqual(order.catering_state, "dispatched")
        self.assertEqual(order.transporter_id.name, "Nguyễn Văn A")
        self.assertEqual(order.transporter_id.phone, "0900000001")
        self.assertEqual(order.transporter_id.code, "NVGH-001")
        self.assertEqual(counts["staff_created"], 1)

    def test_fetch_updates_transporter_for_delivered(self):
        partner = self.env["res.partner"].create(
            {"name": "Trường cập nhật", "is_company": True}
        )
        self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": "DH-TRANS-002",
                "hnck_order": True,
            }
        )
        counts = self._fetch(
            [
                _order_payload(
                    code="DH-TRANS-002",
                    status="DA_GIAO",
                    transporter={"name": "Trần Văn B"},
                )
            ]
        )
        self.assertEqual(counts["updated"], 1)
        order = self._order("DH-TRANS-002")
        self.assertEqual(order.catering_state, "delivered")
        self.assertEqual(order.transporter_id.name, "Trần Văn B")

    def test_fetch_skips_transporter_for_other_status(self):
        counts = self._fetch(
            [_order_payload(code="DH-TRANS-003", status="CHO_XAC_NHAN")]
        )
        order = self._order("DH-TRANS-003")
        self.assertEqual(order.catering_state, "draft")
        self.assertFalse(order.transporter_id)
        self.assertEqual(counts["staff_created"], 0)

    def test_transporter_reused_across_orders(self):
        driver = {"name": "Nguyễn Văn Chung"}
        counts = self._fetch(
            [
                _order_payload(code="DH-TRANS-004", transporter=driver),
                _order_payload(code="DH-TRANS-005", transporter=driver),
            ]
        )
        staff = self.env["set_top_menu.delivery.staff"].search(
            [("name", "=", "Nguyễn Văn Chung")]
        )
        self.assertEqual(len(staff), 1)
        self.assertEqual(staff.order_count, 2)
        self.assertEqual(counts["staff_created"], 1)

    def test_transporter_string_and_missing(self):
        no_driver = _order_payload(code="DH-TRANS-007")
        del no_driver["transporter"]
        self._fetch(
            [
                _order_payload(
                    code="DH-TRANS-006", transporter="Trần Thị B"
                ),
                no_driver,
            ]
        )
        order = self._order("DH-TRANS-006")
        self.assertEqual(order.transporter_id.name, "Trần Thị B")
        self.assertFalse(self._order("DH-TRANS-007").transporter_id)

    def test_daily_form_shows_transporter(self):
        arch = self.env.ref("set_top_menu.view_daily_order_form").arch_db
        self.assertIn('name="transporter_id"', arch)

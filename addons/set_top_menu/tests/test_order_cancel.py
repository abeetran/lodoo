import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderCancel(TransactionCase):
    def _order(self, reference="DH-CANCEL-001"):
        partner = self.env["res.partner"].create(
            {"name": "Khách huỷ đơn", "is_company": True}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )

    def _cancel_wizard(self, order, reason="Khách đổi ý"):
        return self.env["set_top_menu.order.cancel.wizard"].create(
            {"order_id": order.id, "reason": reason}
        )

    def _bodies(self, order):
        return " ".join(order.message_ids.mapped("body") or [])

    def test_cancel_button_opens_reason_popup(self):
        order = self._order()
        result = order.action_cancel_order()
        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(
            result["res_model"], "set_top_menu.order.cancel.wizard"
        )
        self.assertEqual(result["target"], "new")
        self.assertEqual(
            result["context"]["default_order_id"], order.id
        )
        self.assertEqual(order.catering_state, "draft")

    def test_cancel_from_draft(self):
        order = self._order()
        result = self._cancel_wizard(order).action_confirm_cancel()
        self.assertEqual(result, {"type": "ir.actions.act_window_close"})
        self.assertEqual(order.catering_state, "cancelled")
        bodies = self._bodies(order)
        self.assertIn("Khách đổi ý", bodies)
        self.assertIn("Chờ xác nhận", bodies)
        self.assertIn("Đã hủy", bodies)

    def test_cancel_from_confirmed(self):
        order = self._order("DH-CANCEL-002")
        order.write({"catering_state": "confirmed"})
        self._cancel_wizard(order, "Hết nguyên liệu").action_confirm_cancel()
        self.assertEqual(order.catering_state, "cancelled")
        bodies = self._bodies(order)
        self.assertIn("Hết nguyên liệu", bodies)
        self.assertIn("Đã xác nhận", bodies)
        self.assertIn("Đã hủy", bodies)

    def test_cancel_requires_reason(self):
        order = self._order("DH-CANCEL-004")
        wizard = self.env["set_top_menu.order.cancel.wizard"].create(
            {"order_id": order.id}
        )
        with self.assertRaises(UserError):
            wizard.action_confirm_cancel()
        self.assertEqual(order.catering_state, "draft")
        self.assertFalse(order.message_ids)

    def test_discard_cancel_logs_reason(self):
        order = self._order("DH-CANCEL-005")
        result = self._cancel_wizard(
            order, "Nhập nhầm, giữ lại đơn"
        ).action_discard_cancel()
        self.assertEqual(result, {"type": "ir.actions.act_window_close"})
        self.assertEqual(order.catering_state, "draft")
        bodies = self._bodies(order)
        self.assertIn("Nhập nhầm, giữ lại đơn", bodies)
        self.assertIn("huỷ bỏ", bodies)

    def test_discard_empty_closes_silently(self):
        order = self._order("DH-CANCEL-006")
        wizard = self.env["set_top_menu.order.cancel.wizard"].create(
            {"order_id": order.id}
        )
        result = wizard.action_discard_cancel()
        self.assertEqual(result, {"type": "ir.actions.act_window_close"})
        self.assertEqual(order.catering_state, "draft")
        self.assertFalse(order.message_ids)

    def test_status_changes_logged_to_chatter(self):
        order = self._order("DH-CANCEL-007")
        order.action_confirm()
        order.write({"catering_state": "in_production"})
        bodies = self._bodies(order)
        self.assertIn("Chờ xác nhận → Đã xác nhận", bodies)
        self.assertIn("Đã xác nhận → Đang chuẩn bị", bodies)

    def test_cancel_blocked_once_in_production(self):
        order = self._order("DH-CANCEL-003")
        order.write({"catering_state": "in_production"})
        with self.assertRaises(UserError):
            order.action_cancel_order()
        self.assertEqual(order.catering_state, "in_production")

    def test_daily_form_has_cancel_button_hidden_for_hnck(self):
        arch = self.env.ref("set_top_menu.view_daily_order_form").arch_db
        self.assertIn('name="action_cancel_order"', arch)
        self.assertIn('string="Huỷ đơn"', arch)
        self.assertIn(
            'invisible="not id or hnck_order or catering_state not in '
            "('draft', 'confirmed')\"",
            arch,
        )

    def test_sale_form_has_cancel_button_hidden_for_hnck(self):
        arch = self.env.ref("set_top_menu.view_order_form_menu_item").arch_db
        self.assertIn('name="action_cancel_order"', arch)
        self.assertIn(
            'invisible="not id or hnck_order or catering_state not in '
            "('draft', 'confirmed')\"",
            arch,
        )

    def test_cancel_reason_field_full_width(self):
        arch = self.env.ref("set_top_menu.view_order_cancel_wizard_form").arch_db
        sheet = ET.fromstring(arch).find("sheet")
        direct = [
            node
            for node in sheet.findall("field")
            if node.get("name") == "reason"
        ]
        self.assertEqual(len(direct), 1)

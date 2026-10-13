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

    def test_cancel_from_draft(self):
        order = self._order()
        order.action_cancel_order()
        self.assertEqual(order.catering_state, "cancelled")

    def test_cancel_from_confirmed(self):
        order = self._order("DH-CANCEL-002")
        order.write({"catering_state": "confirmed"})
        order.action_cancel_order()
        self.assertEqual(order.catering_state, "cancelled")

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
            'invisible="hnck_order or catering_state not in '
            "('draft', 'confirmed')\"",
            arch,
        )

    def test_sale_form_has_cancel_button_hidden_for_hnck(self):
        arch = self.env.ref("set_top_menu.view_order_form_menu_item").arch_db
        self.assertIn('name="action_cancel_order"', arch)
        self.assertIn(
            'invisible="hnck_order or catering_state not in '
            "('draft', 'confirmed')\"",
            arch,
        )

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderPreparation(TransactionCase):
    def _order(self, reference="DH-PREP-001"):
        partner = self.env["res.partner"].create(
            {"name": "Khách chuẩn bị", "is_company": True}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )

    def test_start_preparation_from_confirmed(self):
        order = self._order()
        order.write({"catering_state": "confirmed"})
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")

    def test_start_preparation_requires_confirmed(self):
        order = self._order()
        with self.assertRaises(UserError):
            order.action_start_preparation()
        self.assertEqual(order.catering_state, "draft")
        order.write({"catering_state": "ready"})
        with self.assertRaises(UserError):
            order.action_start_preparation()
        self.assertEqual(order.catering_state, "ready")

    def test_daily_form_has_preparation_button(self):
        arch = self.env.ref("set_top_menu.view_daily_order_form").arch_db
        self.assertIn('name="action_start_preparation"', arch)
        self.assertIn('string="Chuẩn bị"', arch)
        self.assertIn(
            'invisible="hnck_order or catering_state != \'confirmed\'"',
            arch,
        )

    def test_daily_form_hides_confirm_once_confirmed(self):
        arch = self.env.ref("set_top_menu.view_daily_order_form").arch_db
        self.assertIn('name="action_confirm"', arch)
        self.assertIn(
            'invisible="hnck_order or catering_state != \'draft\'"',
            arch,
        )

    def test_sale_form_has_preparation_button(self):
        arch = self.env.ref("set_top_menu.view_order_form_menu_item").arch_db
        self.assertIn('name="action_start_preparation"', arch)
        self.assertIn('invisible="catering_state != \'confirmed\'"', arch)

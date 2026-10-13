from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderCancelPreparation(TransactionCase):
    def _order(self, reference="DH-UNPREP-001"):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )

    def _dish(self, code):
        uom = self.env.ref("uom.product_uom_unit")
        return self.env["set_top_menu.menu.item"].create(
            {
                "name": "Món %s" % code,
                "item_code": code,
                "serving_size": 1.0,
                "serving_uom_id": uom.id,
            }
        )

    def test_cancel_preparation_without_plans(self):
        order = self._order()
        order.write({"catering_state": "in_production"})
        order.action_cancel_preparation()
        self.assertEqual(order.catering_state, "confirmed")

    def test_cancel_preparation_requires_in_production(self):
        order = self._order("DH-UNPREP-002")
        with self.assertRaises(UserError):
            order.action_cancel_preparation()
        order.write({"catering_state": "confirmed"})
        with self.assertRaises(UserError):
            order.action_cancel_preparation()
        self.assertEqual(order.catering_state, "confirmed")

    def test_cancel_preparation_blocked_with_plans(self):
        order = self._order("DH-UNPREP-003")
        order.write({"catering_state": "in_production"})
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        self.env["set_top_menu.kitchen.plan"].create(
            {"meal_type_id": meal.id, "order_ids": [(4, order.id)]}
        )
        with self.assertRaises(UserError):
            order.action_cancel_preparation()
        self.assertEqual(order.catering_state, "in_production")

    def test_prepare_saves_source_orders(self):
        dish = self._dish("MON-SRC-001")
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        order = self._order("DH-UNPREP-004")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": 2.0,
            }
        )
        order.write({"catering_state": "confirmed"})
        order.action_start_preparation()
        plans = order.kitchen_plan_ids
        self.assertTrue(plans)
        for plan in plans:
            self.assertIn(order, plan.order_ids)

    def test_daily_form_has_cancel_preparation_button(self):
        arch = self.env.ref("set_top_menu.view_daily_order_form").arch_db
        self.assertIn('name="action_cancel_preparation"', arch)
        self.assertIn('string="Huỷ chuẩn bị"', arch)
        self.assertIn(
            'invisible="hnck_order or catering_state != \'in_production\'"',
            arch,
        )

    def test_sale_form_has_cancel_preparation_button(self):
        arch = self.env.ref("set_top_menu.view_order_form_menu_item").arch_db
        self.assertIn('name="action_cancel_preparation"', arch)
        self.assertIn(
            'invisible="hnck_order or catering_state != \'in_production\'"',
            arch,
        )

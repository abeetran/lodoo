import xml.etree.ElementTree as ET

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

    def test_confirm_creates_no_plans(self):
        dish = self._dish("MON-NOPLAN-001")
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        order = self._order("DH-PREP-002")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": 2.0,
            }
        )
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.catering_state, "confirmed")
        self.assertFalse(order.kitchen_plan_ids)

    def test_confirm_ignores_uom_mismatch(self):
        gram = self.env.ref("uom.product_uom_gram")
        kilo = self.env.ref("uom.product_uom_kgm")
        dish = self._dish("MON-NOPLAN-002")
        dish.serving_uom_id = kilo
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        template = self.env["product.template"].create({"name": "SP gam"})
        order = self._order("DH-PREP-003")
        line_model = self.env["sale.order.line"]
        line_model.create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": 2.0,
            }
        )
        line_model.create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom": gram.id,
                "product_uom_qty": 500.0,
            }
        )
        order.action_confirm()
        self.assertEqual(order.catering_state, "confirmed")
        self.assertFalse(order.kitchen_plan_ids)

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

    def test_daily_form_status_buttons_ask_confirmation(self):
        view = self.env.ref("set_top_menu.view_daily_order_form")
        form = ET.fromstring(view.arch_db)
        for name in (
            "action_confirm",
            "action_start_preparation",
            "action_cancel_preparation",
        ):
            button = form.find(".//button[@name='%s']" % name)
            self.assertTrue(button.get("confirm"))
        cancel = form.find(".//button[@name='action_cancel_order']")
        self.assertIsNone(cancel.get("confirm"))

    def test_sale_form_status_buttons_ask_confirmation(self):
        view = self.env.ref("set_top_menu.view_order_form_menu_item")
        arch = ET.fromstring(view.arch_db)
        for name in (
            "action_start_preparation",
            "action_cancel_preparation",
        ):
            button = arch.find(".//button[@name='%s']" % name)
            self.assertTrue(button.get("confirm"))
        xpaths = [
            node
            for node in arch.iter("xpath")
            if node.get("position") == "attributes"
            and "action_confirm" in (node.get("expr") or "")
        ]
        self.assertEqual(len(xpaths), 1)
        confirm = xpaths[0].find("attribute[@name='confirm']")
        self.assertEqual(confirm.text, "Xác nhận đơn hàng này?")

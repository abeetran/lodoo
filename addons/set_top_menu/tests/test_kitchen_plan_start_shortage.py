from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestKitchenPlanStartShortage(TransactionCase):
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

    def _material(self, name, quantity=0.0):
        template = self.env["product.template"].create(
            {"name": name, "type": "product"}
        )
        product = template.product_variant_id
        if quantity:
            location = self.env.ref("stock.stock_location_stock")
            self.env["stock.quant"]._update_available_quantity(
                product, location, quantity
            )
        return product

    def _ingredient(self, dish, product, per_serving):
        uom = self.env.ref("uom.product_uom_unit")
        return self.env["set_top_menu.menu.ingredient"].create(
            {
                "menu_item_id": dish.id,
                "product_id": product.id,
                "quantity": per_serving,
                "uom_id": uom.id,
            }
        )

    def _confirmed_plan(self, dish, quantity):
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        plan = self.env["set_top_menu.kitchen.plan"].create(
            {"meal_type_id": meal.id}
        )
        self.env["set_top_menu.kitchen.plan.line"].create(
            {
                "plan_id": plan.id,
                "menu_item_id": dish.id,
                "quantity": quantity,
            }
        )
        plan.action_confirm()
        return plan

    def test_line_start_blocked_on_shortage(self):
        dish = self._dish("MON-START-SHORT")
        self._ingredient(dish, self._material("Thịt chặn", quantity=1.0), 2.0)
        plan = self._confirmed_plan(dish, 3.0)
        line = plan.line_ids
        self.assertTrue(line.material_shortage)
        with self.assertRaises(UserError) as ctx:
            line.action_start()
        self.assertIn("Mua NVL", str(ctx.exception))
        self.assertIn("Thịt chặn", str(ctx.exception))
        self.assertEqual(line.state, "pending")
        self.assertEqual(plan.state, "confirmed")

    def test_plan_start_blocked_on_shortage(self):
        dish = self._dish("MON-PLAN-SHORT")
        self._ingredient(dish, self._material("Rau chặn"), 1.5)
        plan = self._confirmed_plan(dish, 2.0)
        with self.assertRaises(UserError) as ctx:
            plan.action_start()
        self.assertIn("Mua NVL", str(ctx.exception))
        self.assertEqual(plan.state, "confirmed")
        self.assertEqual(plan.line_ids.state, "pending")

    def test_start_allowed_when_stock_enough(self):
        dish = self._dish("MON-START-ENOUGH")
        self._ingredient(dish, self._material("Thịt đủ", quantity=6.0), 2.0)
        plan = self._confirmed_plan(dish, 3.0)
        plan.action_start()
        self.assertEqual(plan.state, "progress")
        plan.line_ids.action_start()
        self.assertEqual(plan.line_ids.state, "progress")

    def test_start_allowed_without_ingredients(self):
        dish = self._dish("MON-START-NONE")
        plan = self._confirmed_plan(dish, 3.0)
        plan.action_start()
        self.assertEqual(plan.state, "progress")

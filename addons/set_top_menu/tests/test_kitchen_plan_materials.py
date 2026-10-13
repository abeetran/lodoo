import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestKitchenPlanMaterials(TransactionCase):
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

    def _plan_line(self, dish, quantity):
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        plan = self.env["set_top_menu.kitchen.plan"].create(
            {"meal_type_id": meal.id}
        )
        return self.env["set_top_menu.kitchen.plan.line"].create(
            {
                "plan_id": plan.id,
                "menu_item_id": dish.id,
                "quantity": quantity,
            }
        )

    def test_shortage_when_stock_insufficient(self):
        dish = self._dish("MON-NVL-SHORT")
        self._ingredient(dish, self._material("Thịt thiếu"), 2.0)
        line = self._plan_line(dish, 3.0)
        self.assertTrue(line.material_shortage)

    def test_no_shortage_when_stock_covers_exactly(self):
        dish = self._dish("MON-NVL-ENOUGH")
        self._ingredient(dish, self._material("Thịt đủ", quantity=6.0), 2.0)
        line = self._plan_line(dish, 3.0)
        self.assertFalse(line.material_shortage)

    def test_no_shortage_without_ingredients(self):
        dish = self._dish("MON-NVL-NONE")
        line = self._plan_line(dish, 3.0)
        self.assertFalse(line.material_shortage)

    def test_buy_materials_buys_only_shortage(self):
        dish = self._dish("MON-NVL-BUY")
        pork = self._material("Thịt mua", quantity=0.5)
        greens = self._material("Rau mua", quantity=10.0)
        self._ingredient(dish, pork, 0.5)
        self._ingredient(dish, greens, 1.5)
        line = self._plan_line(dish, 4.0)
        self.assertTrue(line.material_shortage)
        action = line.action_buy_materials()
        self.assertEqual(action["res_model"], "purchase.order")
        self.assertEqual(action["view_mode"], "form")
        self.assertNotIn("res_id", action)
        context = action["context"]
        self.assertEqual(
            context["default_company_id"], line.plan_id.company_id.id
        )
        self.assertEqual(context["default_origin"], line.plan_id.name)
        commands = context["default_order_line"]
        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertEqual(command[0], 0)
        self.assertEqual(command[2]["product_id"], pork.id)
        self.assertEqual(command[2]["product_qty"], 1.5)
        self.assertTrue(command[2]["product_uom"])
        self.assertTrue(command[2]["name"])

    def test_buy_materials_with_full_stock_raises(self):
        dish = self._dish("MON-NVL-FULL")
        pork = self._material("Thịt đủ mua", quantity=10.0)
        self._ingredient(dish, pork, 0.5)
        line = self._plan_line(dish, 4.0)
        self.assertFalse(line.material_shortage)
        with self.assertRaises(UserError):
            line.action_buy_materials()

    def test_buy_materials_without_ingredients_raises(self):
        dish = self._dish("MON-NVL-EMPTY")
        line = self._plan_line(dish, 2.0)
        with self.assertRaises(UserError):
            line.action_buy_materials()

    def test_line_tree_has_buy_button_next_to_start(self):
        view = self.env.ref("set_top_menu.view_kitchen_plan_form")
        tree = ET.fromstring(view.arch_db).find(
            ".//field[@name='line_ids']/tree"
        )
        names = [button.get("name") for button in tree.iter("button")]
        self.assertEqual(
            names, ["action_start", "action_buy_materials", "action_done"]
        )
        button = [
            item
            for item in tree.iter("button")
            if item.get("name") == "action_buy_materials"
        ][0]
        self.assertEqual(button.get("string"), "Mua NVL")
        self.assertEqual(
            button.get("invisible"), "state == 'done' or not material_shortage"
        )
        fields = [field.get("name") for field in tree.iter("field")]
        self.assertIn("material_shortage", fields)

    def test_ingredient_uom_mismatch_ignored(self):
        dish = self._dish("MON-UOM-MIX")
        product = self._material("NVL gam")
        gram = self.env.ref("uom.product_uom_gram")
        self.env["set_top_menu.menu.ingredient"].create(
            {
                "menu_item_id": dish.id,
                "product_id": product.id,
                "quantity": 500.0,
                "uom_id": gram.id,
            }
        )
        line = self._plan_line(dish, 1.0)
        self.assertTrue(line.material_shortage)

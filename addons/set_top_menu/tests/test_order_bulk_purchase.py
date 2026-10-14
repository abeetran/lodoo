from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderBulkPurchase(TransactionCase):
    def _product(self, name, product_type="product"):
        template = self.env["product.template"].create(
            {"name": name, "type": product_type}
        )
        return template.product_variant_id

    def _dish(self, code, ingredients):
        uom = self.env.ref("uom.product_uom_unit")
        dish = self.env["set_top_menu.menu.item"].create(
            {
                "name": "Món %s" % code,
                "item_code": code,
                "serving_size": 1.0,
                "serving_uom_id": uom.id,
            }
        )
        for product, per_unit in ingredients:
            self.env["set_top_menu.menu.ingredient"].create(
                {
                    "menu_item_id": dish.id,
                    "product_id": product.id,
                    "quantity": per_unit,
                    "uom_id": uom.id,
                }
            )
        return dish

    def _order(self, reference, line_vals=(), company=None):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        vals = {
            "partner_id": partner.id,
            "catering_reference": reference,
        }
        if company:
            vals["company_id"] = company.id
        order = self.env["sale.order"].create(vals)
        for line in line_vals:
            line = dict(line, order_id=order.id)
            self.env["sale.order.line"].create(line)
        return order

    def _dish_line(self, dish, quantity):
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        return {
            "menu_item_id": dish.id,
            "meal_type_id": meal.id,
            "product_uom_qty": quantity,
        }

    def _po_lines(self, result):
        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "purchase.order")
        self.assertEqual(result["view_mode"], "form")
        commands = result["context"]["default_order_line"]
        return {cmd[2]["product_id"]: cmd[2] for cmd in commands}

    def test_bulk_purchase_aggregates_lines_and_ingredients(self):
        food = self._product("Trái cây gộp")
        ing_a = self._product("Thịt gộp")
        ing_b = self._product("Rau gộp")
        dish = self._dish("MON-BULK-001", [(ing_a, 1.5), (ing_b, 2.0)])
        service = self._product("DV gộp", product_type="service")
        order1 = self._order(
            "DH-BULK-001",
            [
                {"product_id": food.id, "product_uom_qty": 4.0},
                self._dish_line(dish, 2.0),
            ],
        )
        order2 = self._order(
            "DH-BULK-002",
            [
                {"product_id": food.id, "product_uom_qty": 3.0},
                {"product_id": service.id, "product_uom_qty": 1.0},
                {"display_type": "line_note", "name": "Ghi chú"},
            ],
        )
        result = (order1 | order2).action_bulk_purchase()
        lines = self._po_lines(result)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[food.id]["product_qty"], 7.0)
        self.assertEqual(lines[ing_a.id]["product_qty"], 3.0)
        self.assertEqual(lines[ing_b.id]["product_qty"], 4.0)
        self.assertEqual(lines[food.id]["product_uom"], food.uom_po_id.id)
        origin = result["context"]["default_origin"]
        self.assertIn("DH-BULK-001", origin)
        self.assertIn("DH-BULK-002", origin)

    def test_cancelled_orders_skipped(self):
        food = self._product("Trái cây huỷ")
        order1 = self._order(
            "DH-BULK-003", [{"product_id": food.id, "product_uom_qty": 4.0}]
        )
        order2 = self._order(
            "DH-BULK-004", [{"product_id": food.id, "product_uom_qty": 3.0}]
        )
        order2.write({"catering_state": "cancelled"})
        result = (order1 | order2).action_bulk_purchase()
        lines = self._po_lines(result)
        self.assertEqual(lines[food.id]["product_qty"], 4.0)
        self.assertEqual(result["context"]["default_origin"], "DH-BULK-003")

    def test_all_cancelled_raises(self):
        food = self._product("Trái cây huỷ hết")
        order = self._order(
            "DH-BULK-005", [{"product_id": food.id, "product_uom_qty": 4.0}]
        )
        order.write({"catering_state": "cancelled"})
        with self.assertRaises(UserError):
            order.action_bulk_purchase()

    def test_dish_without_ingredients_raises(self):
        dish = self._dish("MON-BULK-EMPTY", [])
        order = self._order("DH-BULK-006", [self._dish_line(dish, 2.0)])
        with self.assertRaises(UserError):
            order.action_bulk_purchase()

    def test_multi_company_raises(self):
        food = self._product("Trái cây cty")
        other = self.env["res.company"].create({"name": "Công ty gộp"})
        order1 = self._order(
            "DH-BULK-007", [{"product_id": food.id, "product_uom_qty": 4.0}]
        )
        order2 = self._order(
            "DH-BULK-008",
            [{"product_id": food.id, "product_uom_qty": 4.0}],
            company=other,
        )
        with self.assertRaises(UserError):
            (order1 | order2).action_bulk_purchase()

    def test_server_action_bound_to_order_list(self):
        action = self.env.ref("set_top_menu.action_sale_order_bulk_purchase")
        self.assertEqual(action.binding_model_id.model, "sale.order")
        self.assertEqual(action.binding_view_types, "list")
        self.assertEqual(action.state, "code")
        self.assertIn("action_bulk_purchase", action.code)

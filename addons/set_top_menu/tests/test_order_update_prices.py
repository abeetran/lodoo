from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderUpdatePrices(TransactionCase):
    def _product(self, name, list_price):
        template = self.env["product.template"].create(
            {"name": name, "type": "product", "list_price": list_price}
        )
        return template.product_variant_id

    def _dish(self, code, sale_price):
        uom = self.env.ref("uom.product_uom_unit")
        return self.env["set_top_menu.menu.item"].create(
            {
                "name": "Món %s" % code,
                "item_code": code,
                "serving_size": 1.0,
                "serving_uom_id": uom.id,
                "sale_price": sale_price,
            }
        )

    def _order(self, reference):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )

    def _dish_line(self, order, dish, quantity):
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": quantity,
            }
        )

    def test_update_prices_refreshes_from_masters(self):
        food = self._product("Thực phẩm giá", 100.0)
        dish = self._dish("MON-PRICE-001", 50.0)
        order = self._order("DH-PRICE-001")
        food_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        dish_line = self._dish_line(order, dish, 3.0)
        self.assertEqual(food_line.price_unit, 100.0)
        self.assertEqual(dish_line.price_unit, 50.0)
        food_line.price_unit = 10.0
        food.product_tmpl_id.list_price = 150.0
        dish.sale_price = 60.0
        self.assertEqual(food_line.price_unit, 10.0)
        self.assertEqual(dish_line.price_unit, 50.0)
        result = order.action_update_prices()
        self.assertEqual(food_line.price_unit, 150.0)
        self.assertEqual(dish_line.price_unit, 60.0)
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "success")
        self.assertIn("1 đơn hàng", result["params"]["message"])

    def test_non_draft_orders_skipped(self):
        food = self._product("Thực phẩm giữ giá", 100.0)
        draft = self._order("DH-PRICE-002")
        draft_line = self.env["sale.order.line"].create(
            {
                "order_id": draft.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        confirmed = self._order("DH-PRICE-003")
        confirmed_line = self.env["sale.order.line"].create(
            {
                "order_id": confirmed.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        confirmed.action_confirm()
        food.product_tmpl_id.list_price = 200.0
        result = (draft | confirmed).action_update_prices()
        self.assertEqual(draft_line.price_unit, 200.0)
        self.assertEqual(confirmed_line.price_unit, 100.0)
        self.assertIn("Bỏ qua 1 đơn", result["params"]["message"])

    def test_no_draft_orders_raises(self):
        food = self._product("Thực phẩm báo lỗi", 100.0)
        order = self._order("DH-PRICE-004")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        order.action_confirm()
        with self.assertRaises(UserError):
            order.action_update_prices()

    def test_hnck_draft_skipped(self):
        food = self._product("Thực phẩm HNCK", 100.0)
        order = self._order("DH-PRICE-005")
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        order.write({"hnck_order": True})
        line.price_unit = 10.0
        with self.assertRaises(UserError):
            order.action_update_prices()
        self.assertEqual(line.price_unit, 10.0)

    def test_server_action_bound_to_order_list(self):
        action = self.env.ref("set_top_menu.action_sale_order_update_prices")
        self.assertEqual(action.binding_model_id.model, "sale.order")
        self.assertEqual(action.binding_view_types, "list")
        self.assertEqual(action.state, "code")
        self.assertIn("action_update_prices", action.code)

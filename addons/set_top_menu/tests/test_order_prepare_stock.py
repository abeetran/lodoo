from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderPrepareStock(TransactionCase):
    def _order(self, reference="DH-STOCK-001"):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )
        order.write({"catering_state": "confirmed"})
        return order

    def _storable(self, name, quantity=0.0):
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

    def _add_line(self, order, product, quantity, **extra):
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": quantity,
                **extra,
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

    def test_prepare_deducts_stock(self):
        product = self._storable("SP trừ kho", quantity=10.0)
        order = self._order()
        self._add_line(order, product, 4.0)
        result = order.action_start_preparation()
        self.assertNotIsInstance(result, dict)
        self.assertEqual(order.catering_state, "in_production")
        self.assertEqual(product.qty_available, 6.0)

    def test_prepare_shortage_opens_wizard(self):
        product = self._storable("SP thiếu kho", quantity=1.0)
        order = self._order("DH-STOCK-002")
        self._add_line(order, product, 4.0)
        result = order.action_start_preparation()
        self.assertEqual(
            result["res_model"], "set_top_menu.order.shortage.wizard"
        )
        self.assertEqual(result["target"], "new")
        self.assertEqual(order.catering_state, "confirmed")
        self.assertEqual(product.qty_available, 1.0)
        wizard = self.env["set_top_menu.order.shortage.wizard"].browse(
            result["res_id"]
        )
        self.assertEqual(wizard.order_id, order)
        self.assertIn("SP thiếu kho", wizard.message)

    def test_wizard_confirm_opens_po_with_shortage(self):
        product = self._storable("SP mua bù", quantity=1.0)
        order = self._order("DH-STOCK-003")
        self._add_line(order, product, 4.0)
        result = order.action_start_preparation()
        wizard = self.env["set_top_menu.order.shortage.wizard"].browse(
            result["res_id"]
        )
        action = wizard.action_confirm_purchase()
        self.assertEqual(action["res_model"], "purchase.order")
        self.assertEqual(action["view_mode"], "form")
        self.assertNotIn("res_id", action)
        context = action["context"]
        self.assertEqual(
            context["default_company_id"], order.company_id.id
        )
        self.assertEqual(context["default_origin"], "DH-STOCK-003")
        commands = context["default_order_line"]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][2]["product_id"], product.id)
        self.assertEqual(commands[0][2]["product_qty"], 3.0)

    def test_wizard_confirm_with_arrived_stock_raises(self):
        product = self._storable("SP về kho", quantity=1.0)
        order = self._order("DH-STOCK-004")
        self._add_line(order, product, 4.0)
        result = order.action_start_preparation()
        wizard = self.env["set_top_menu.order.shortage.wizard"].browse(
            result["res_id"]
        )
        location = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"]._update_available_quantity(
            product, location, 10.0
        )
        with self.assertRaises(UserError):
            wizard.action_confirm_purchase()

    def test_prepare_ignores_dish_and_service_lines(self):
        dish = self._dish("MON-STOCK-SKIP")
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        service_template = self.env["product.template"].create(
            {"name": "Phí phục vụ", "type": "service"}
        )
        order = self._order("DH-STOCK-005")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": 2.0,
            }
        )
        self._add_line(order, service_template.product_variant_id, 1.0)
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")

    def test_prepare_multi_short_raises(self):
        first = self._order("DH-STOCK-006")
        self._add_line(
            first, self._storable("SP thiếu 1"), 2.0
        )
        second = self._order("DH-STOCK-007")
        self._add_line(
            second, self._storable("SP thiếu 2"), 3.0
        )
        with self.assertRaises(UserError):
            (first + second).action_start_preparation()
        self.assertEqual(first.catering_state, "confirmed")
        self.assertEqual(second.catering_state, "confirmed")

    def test_shortage_wizard_view(self):
        arch = self.env.ref(
            "set_top_menu.view_order_shortage_wizard_form"
        ).arch_db
        self.assertIn('name="action_confirm_purchase"', arch)
        self.assertIn('name="message"', arch)
        self.assertIn('name="order_id"', arch)

    def test_cancel_preparation_returns_stock(self):
        product = self._storable("SP trả kho", quantity=10.0)
        order = self._order("DH-STOCK-008")
        self._add_line(order, product, 4.0)
        order.action_start_preparation()
        self.assertEqual(product.qty_available, 6.0)
        self.assertTrue(order.stock_deducted)
        order.action_cancel_preparation()
        self.assertEqual(order.catering_state, "confirmed")
        self.assertEqual(product.qty_available, 10.0)
        self.assertFalse(order.stock_deducted)

    def test_cancel_preparation_without_deduct_adds_nothing(self):
        product = self._storable("SP không trừ", quantity=10.0)
        order = self._order("DH-STOCK-009")
        self._add_line(order, product, 4.0)
        order.write({"catering_state": "in_production"})
        self.assertFalse(order.stock_deducted)
        order.action_cancel_preparation()
        self.assertEqual(order.catering_state, "confirmed")
        self.assertEqual(product.qty_available, 10.0)

    def test_cancel_preparation_blocked_keeps_stock(self):
        product = self._storable("SP giữ kho", quantity=10.0)
        order = self._order("DH-STOCK-010")
        self._add_line(order, product, 4.0)
        order.action_start_preparation()
        self.assertEqual(product.qty_available, 6.0)
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        self.env["set_top_menu.kitchen.plan"].create(
            {"meal_type_id": meal.id, "order_ids": [(4, order.id)]}
        )
        with self.assertRaises(UserError):
            order.action_cancel_preparation()
        self.assertEqual(order.catering_state, "in_production")
        self.assertEqual(product.qty_available, 6.0)
        self.assertTrue(order.stock_deducted)

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

    def test_prepare_ignores_uom_mismatch(self):
        gram = self.env.ref("uom.product_uom_gram")
        product = self._storable("SP gam", quantity=1000.0)
        order = self._order("DH-STOCK-011")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom": gram.id,
                "product_uom_qty": 500.0,
            }
        )
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        self.assertEqual(product.qty_available, 500.0)

    def test_prepare_shortage_ignores_uom_mismatch(self):
        gram = self.env.ref("uom.product_uom_gram")
        product = self._storable("SP gam thiếu", quantity=100.0)
        order = self._order("DH-STOCK-012")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom": gram.id,
                "product_uom_qty": 500.0,
            }
        )
        result = order.action_start_preparation()
        self.assertEqual(
            result["res_model"], "set_top_menu.order.shortage.wizard"
        )
        wizard = self.env["set_top_menu.order.shortage.wizard"].browse(
            result["res_id"]
        )
        action = wizard.action_confirm_purchase()
        commands = action["context"]["default_order_line"]
        self.assertEqual(commands[0][2]["product_qty"], 400.0)

    def test_prepare_with_dishes_ignores_uom_mismatch(self):
        gram = self.env.ref("uom.product_uom_gram")
        product = self._storable("SP gam món", quantity=1000.0)
        dish = self._dish("MON-UOM-PREP")
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        order = self._order("DH-STOCK-013")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom": gram.id,
                "product_uom_qty": 500.0,
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": 2.0,
            }
        )
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        self.assertEqual(len(order.kitchen_plan_ids), 1)
        self.assertEqual(product.qty_available, 500.0)

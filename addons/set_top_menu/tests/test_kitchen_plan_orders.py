import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestKitchenPlanOrders(TransactionCase):
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

    def _order(self, reference, lines, hnck_order=False):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
                "hnck_order": hnck_order,
            }
        )
        line_model = self.env["sale.order.line"].with_context(
            hnck_sync=True
        ) if hnck_order else self.env["sale.order.line"]
        for dish, quantity in lines:
            line_model.create(
                {
                    "order_id": order.id,
                    "menu_item_id": dish.id,
                    "meal_type_id": meal.id,
                    "product_uom_qty": quantity,
                }
            )
        return order

    def test_prepare_creates_plans_from_dishes(self):
        dish_a = self._dish("MON-PLAN-A")
        dish_b = self._dish("MON-PLAN-B")
        order = self._order(
            "DH-PLAN-001", [(dish_a, 2.0), (dish_b, 3.0)]
        )
        order.write({"catering_state": "confirmed"})
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        plans = order.kitchen_plan_ids
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans.state, "confirmed")
        self.assertIn(order, plans.order_ids)
        got = {
            line.menu_item_id: line.quantity for line in plans.line_ids
        }
        self.assertEqual(got, {dish_a: 2.0, dish_b: 3.0})

    def test_prepare_defaults_missing_meal_to_lunch(self):
        dish_a = self._dish("MON-LUNCH-A")
        dish_b = self._dish("MON-LUNCH-B")
        partner = self.env["res.partner"].create(
            {"name": "Khách Lunch", "is_company": True}
        )
        lunch = self.env.ref("set_top_menu.meal_type_lunch")
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": "DH-LUNCH-001",
            }
        )
        line_model = self.env["sale.order.line"]
        line_model.create(
            {
                "order_id": order.id,
                "menu_item_id": dish_a.id,
                "product_uom_qty": 2.0,
            }
        )
        line_model.create(
            {
                "order_id": order.id,
                "menu_item_id": dish_b.id,
                "meal_type_id": lunch.id,
                "product_uom_qty": 3.0,
            }
        )
        order.write({"catering_state": "confirmed"})
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        plans = order.kitchen_plan_ids
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans.meal_type_id, lunch)
        got = {
            line.menu_item_id: line.quantity for line in plans.line_ids
        }
        self.assertEqual(got, {dish_a: 2.0, dish_b: 3.0})

    def test_prepare_skips_plan_when_no_dishes(self):
        template = self.env["product.template"].create(
            {"name": "SP thường", "type": "product"}
        )
        product = template.product_variant_id
        location = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"]._update_available_quantity(
            product, location, 5.0
        )
        partner = self.env["res.partner"].create(
            {"name": "Khách không món", "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": "DH-PLAN-002",
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 2.0,
            }
        )
        order.write({"catering_state": "confirmed"})
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        self.assertFalse(order.kitchen_plan_ids)

    def test_prepare_skips_plan_for_hnck(self):
        dish = self._dish("MON-PLAN-HNCK")
        order = self._order(
            "DH-PLAN-003", [(dish, 2.0)], hnck_order=True
        )
        order.write({"catering_state": "confirmed"})
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        self.assertFalse(order.kitchen_plan_ids)

    def test_prepare_keeps_existing_plans(self):
        dish = self._dish("MON-PLAN-DUP")
        order = self._order("DH-PLAN-004", [(dish, 2.0)])
        order.write({"catering_state": "confirmed"})
        order._create_kitchen_plans()
        self.assertEqual(len(order.kitchen_plan_ids), 1)
        order.action_start_preparation()
        self.assertEqual(len(order.kitchen_plan_ids), 1)

    def test_onchange_orders_fills_aggregated_lines(self):
        dish_a = self._dish("MON-AGG-A")
        dish_b = self._dish("MON-AGG-B")
        first = self._order("DH-AGG-001", [(dish_a, 2.0)])
        second = self._order(
            "DH-AGG-002", [(dish_a, 3.0), (dish_b, 1.0)]
        )
        (first + second).write({"catering_state": "in_production"})
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        plan = self.env["set_top_menu.kitchen.plan"].new(
            {
                "meal_type_id": meal.id,
                "order_ids": [(6, 0, (first + second).ids)],
            }
        )
        result = plan._onchange_order_ids_fill_lines()
        self.assertIsNone(result)
        got = {
            line.menu_item_id: line.quantity for line in plan.line_ids
        }
        self.assertEqual(got, {dish_a: 5.0, dish_b: 1.0})

    def test_onchange_orders_without_dishes_warns(self):
        product = self.env["product.product"].search([], limit=1)
        partner = self.env["res.partner"].create(
            {"name": "Khách không món 2", "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": "DH-AGG-003",
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 2.0,
            }
        )
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        plan = self.env["set_top_menu.kitchen.plan"].new(
            {"meal_type_id": meal.id, "order_ids": [(6, 0, [order.id])]}
        )
        result = plan._onchange_order_ids_fill_lines()
        self.assertFalse(plan.line_ids)
        self.assertIn("warning", result)

    def test_order_selector_config(self):
        field = self.env["set_top_menu.kitchen.plan"]._fields["order_ids"]
        self.assertEqual(
            field.domain,
            [
                ("catering_state", "=", "in_production"),
                ("order_line.menu_item_id", "!=", False),
            ],
        )
        arch = self.env.ref("set_top_menu.view_kitchen_plan_form").arch_db
        self.assertIn('name="order_ids"', arch)
        self.assertIn('string="Chứng từ gốc"', arch)
        self.assertIn('readonly="state != \'draft\'"', arch)


class TestKitchenPlanLineUom(TransactionCase):
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

    def _plan(self):
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        return self.env["set_top_menu.kitchen.plan"].create(
            {"meal_type_id": meal.id}
        )

    def test_line_uom_defaults_to_serving_uom(self):
        dish = self._dish("MON-UOM-DEF")
        line = self.env["set_top_menu.kitchen.plan.line"].create(
            {
                "plan_id": self._plan().id,
                "menu_item_id": dish.id,
                "quantity": 2.0,
            }
        )
        self.assertEqual(line.uom_id, dish.serving_uom_id)

    def test_line_uom_editable(self):
        dish = self._dish("MON-UOM-EDIT")
        line = self.env["set_top_menu.kitchen.plan.line"].create(
            {
                "plan_id": self._plan().id,
                "menu_item_id": dish.id,
                "quantity": 2.0,
            }
        )
        kilo = self.env.ref("uom.product_uom_kgm")
        line.write({"uom_id": kilo.id})
        self.assertEqual(line.uom_id, kilo)
        self.assertEqual(
            dish.serving_uom_id, self.env.ref("uom.product_uom_unit")
        )

    def test_onchange_dish_sets_uom(self):
        dish = self._dish("MON-UOM-ONCH")
        line = self.env["set_top_menu.kitchen.plan.line"].new({})
        line.menu_item_id = dish
        line._onchange_menu_item_id_set_uom()
        self.assertEqual(line.uom_id, dish.serving_uom_id)
        line.menu_item_id = False
        line._onchange_menu_item_id_set_uom()
        self.assertFalse(line.uom_id)

    def test_line_tree_uom_editable_in_draft(self):
        view = self.env.ref("set_top_menu.view_kitchen_plan_form")
        tree = ET.fromstring(view.arch_db).find(
            ".//field[@name='line_ids']/tree"
        )
        uom = [
            field
            for field in tree.iter("field")
            if field.get("name") == "uom_id"
        ][0]
        self.assertEqual(uom.get("readonly"), "parent.state != 'draft'")


class TestGenerateFromOrders(TransactionCase):
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

    def _order(self, reference, dish, quantity, catering_state):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": quantity,
            }
        )
        order.write({"catering_state": catering_state})
        return order

    def _plan(self):
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        return self.env["set_top_menu.kitchen.plan"].create(
            {"meal_type_id": meal.id}
        )

    def test_generate_takes_preparing_orders_without_plans(self):
        dish_a = self._dish("MON-GEN-A")
        dish_b = self._dish("MON-GEN-B")
        dish_c = self._dish("MON-GEN-C")
        order_a = self._order("DH-GEN-001", dish_a, 2.0, "in_production")
        order_b = self._order("DH-GEN-002", dish_b, 3.0, "in_production")
        self._order("DH-GEN-003", dish_c, 1.0, "confirmed")
        self.env["set_top_menu.kitchen.plan"].create(
            {
                "meal_type_id": self.env.ref(
                    "set_top_menu.meal_type_lunch"
                ).id,
                "order_ids": [(4, order_b.id)],
            }
        )
        plan = self._plan()
        result = plan.action_generate_from_orders()
        self.assertTrue(result)
        self.assertEqual(plan.order_ids, order_a)
        got = {
            line.menu_item_id: line.quantity for line in plan.line_ids
        }
        self.assertEqual(got, {dish_a: 2.0})

    def test_generate_all_have_plans_notifies(self):
        dish = self._dish("MON-GEN-PLAN")
        order = self._order("DH-GEN-004", dish, 2.0, "in_production")
        self.env["set_top_menu.kitchen.plan"].create(
            {
                "meal_type_id": self.env.ref(
                    "set_top_menu.meal_type_lunch"
                ).id,
                "order_ids": [(4, order.id)],
            }
        )
        plan = self._plan()
        result = plan.action_generate_from_orders()
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertIn("đều đã tồn tại", result["params"]["message"])
        self.assertFalse(plan.order_ids)
        self.assertFalse(plan.line_ids)

    def test_generate_no_preparing_orders_notifies(self):
        plan = self._plan()
        result = plan.action_generate_from_orders()
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertIn(
            "Không có đơn hàng Đang chuẩn bị",
            result["params"]["message"],
        )

    def test_generate_without_dishes_raises(self):
        template = self.env["product.template"].create(
            {"name": "SP không món", "type": "product"}
        )
        partner = self.env["res.partner"].create(
            {"name": "Khách không món", "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": "DH-GEN-005",
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 2.0,
            }
        )
        order.write({"catering_state": "in_production"})
        with self.assertRaises(UserError):
            self._plan().action_generate_from_orders()

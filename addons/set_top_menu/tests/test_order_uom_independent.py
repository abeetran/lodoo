from odoo.tests.common import TransactionCase


class TestOrderUomIndependent(TransactionCase):
    def _selling_uom(self, name):
        category = self.env["uom.category"].create(
            {"name": "Nhóm bán %s" % name}
        )
        return self.env["uom.uom"].create(
            {
                "name": name,
                "category_id": category.id,
                "uom_type": "reference",
                "factor": 1.0,
                "rounding": 0.01,
            }
        )

    def _storable(self, name, stock_uom, quantity=0.0):
        template = self.env["product.template"].create(
            {
                "name": name,
                "type": "product",
                "uom_id": stock_uom.id,
                "uom_po_id": stock_uom.id,
            }
        )
        product = template.product_variant_id
        if quantity:
            location = self.env.ref("stock.stock_location_stock")
            self.env["stock.quant"]._update_available_quantity(
                product, location, quantity
            )
        return product

    def _order(self, reference, product, quantity, selling_uom):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom": selling_uom.id,
                "product_uom_qty": quantity,
            }
        )
        return order

    def _dish(self, code, serving_uom):
        return self.env["set_top_menu.menu.item"].create(
            {
                "name": "Món %s" % code,
                "item_code": code,
                "serving_size": 1.0,
                "serving_uom_id": serving_uom.id,
            }
        )

    def test_confirm_cross_category_keeps_raw_qty_in_stock_uom(self):
        unit = self.env.ref("uom.product_uom_unit")
        product = self._storable("Trái cây thùng", unit, quantity=100.0)
        thung = self._selling_uom("Thùng")
        order = self._order("DH-UOM-001", product, 5.0, thung)
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(len(order.picking_ids), 1)
        move = order.picking_ids.move_ids
        self.assertEqual(len(move), 1)
        self.assertEqual(move.product_uom, product.uom_id)
        self.assertEqual(move.product_uom_qty, 5.0)

    def test_validate_cross_category_delivered_raw_qty(self):
        unit = self.env.ref("uom.product_uom_unit")
        product = self._storable("Trái cây giao", unit, quantity=100.0)
        thung = self._selling_uom("Thùng giao")
        order = self._order("DH-UOM-002", product, 5.0, thung)
        order.action_confirm()
        picking = order.picking_ids
        picking.user_id = self.env.ref("base.user_admin").id
        picking.button_validate()
        self.assertEqual(picking.state, "delivering")
        picking.move_ids.quantity = 5.0
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        line = order.order_line
        self.assertEqual(line.qty_delivered, 5.0)
        line._action_launch_stock_rule()
        self.assertEqual(len(order.picking_ids), 1)

    def test_same_category_keeps_core_conversion(self):
        gram = self.env.ref("uom.product_uom_gram")
        kilo = self.env.ref("uom.product_uom_kgm")
        product = self._storable("Bột mì", kilo)
        order = self._order("DH-UOM-003", product, 500.0, gram)
        order.action_confirm()
        move = order.picking_ids.move_ids
        self.assertEqual(move.product_uom, kilo)
        self.assertEqual(move.product_uom_qty, 0.5)

    def test_prepare_dish_cross_category_creates_draft_plan(self):
        phan_an = self._selling_uom("Phần ăn")
        dish = self._dish("MON-UOM-001", phan_an)
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        partner = self.env["res.partner"].create(
            {"name": "Khách DH-UOM-004", "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": "DH-UOM-004",
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": 2.0,
            }
        )
        self.assertEqual(line.product_uom, phan_an)
        order.action_confirm()
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        self.assertEqual(len(order.kitchen_plan_ids), 1)
        self.assertEqual(order.kitchen_plan_ids.state, "draft")

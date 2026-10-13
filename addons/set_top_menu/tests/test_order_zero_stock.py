from odoo.tests.common import TransactionCase


class TestOrderZeroStock(TransactionCase):
    def _order_with_line(self, reference, product, quantity=5.0):
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
                "product_uom_qty": quantity,
            }
        )
        return order

    def _storable_product(self, name):
        template = self.env["product.template"].create(
            {"name": name, "type": "product"}
        )
        return template.product_variant_id

    def test_create_and_confirm_with_zero_stock(self):
        product = self._storable_product("SP hết hàng")
        self.assertEqual(product.qty_available, 0.0)
        order = self._order_with_line("DH-ZERO-001", product)
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.catering_state, "confirmed")

    def test_stock_column_reflects_on_hand(self):
        product = self._storable_product("SP còn hàng")
        location = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"]._update_available_quantity(
            product, location, 7.0
        )
        order = self._order_with_line("DH-ZERO-002", product)
        self.assertEqual(order.order_line.product_stock_qty, 7.0)

    def test_stock_column_config(self):
        field = self.env["sale.order.line"]._fields["product_stock_qty"]
        self.assertEqual(field.related, "product_id.qty_available")
        daily_arch = self.env.ref("set_top_menu.view_daily_order_form").arch_db
        self.assertIn('name="product_stock_qty"', daily_arch)
        sale_arch = self.env.ref(
            "set_top_menu.view_order_form_menu_item"
        ).arch_db
        self.assertIn('name="product_stock_qty"', sale_arch)

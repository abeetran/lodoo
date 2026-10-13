import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderLineBuy(TransactionCase):
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

    def _storable_product(self, name, quantity=0.0):
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

    def test_buy_product_orders_only_shortage(self):
        product = self._storable_product("SP thiếu", quantity=2.0)
        order = self._order_with_line("DH-BUY-001", product, quantity=5.0)
        action = order.order_line.action_buy_product()
        self.assertEqual(action["res_model"], "purchase.order")
        self.assertEqual(action["view_mode"], "form")
        self.assertNotIn("res_id", action)
        context = action["context"]
        self.assertEqual(
            context["default_company_id"], order.company_id.id
        )
        self.assertEqual(context["default_origin"], "DH-BUY-001")
        commands = context["default_order_line"]
        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertEqual(command[0], 0)
        self.assertEqual(command[2]["product_id"], product.id)
        self.assertEqual(command[2]["product_qty"], 3.0)

    def test_buy_product_with_full_stock_raises(self):
        product = self._storable_product("SP đủ", quantity=5.0)
        order = self._order_with_line("DH-BUY-002", product, quantity=5.0)
        with self.assertRaises(UserError):
            order.order_line.action_buy_product()

    def test_buy_product_without_product_raises(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"]
                .create({"name": "Khách tay", "is_company": True})
                .id,
                "catering_reference": "DH-BUY-003",
            }
        )
        line = self.env["sale.order.line"].new({"order_id": order.id})
        with self.assertRaises(UserError):
            line.action_buy_product()

    def test_daily_tree_has_buy_button(self):
        view = self.env.ref("set_top_menu.view_daily_order_form")
        tree = ET.fromstring(view.arch_db).find(
            ".//field[@name='order_line']/tree"
        )
        buttons = {
            button.get("name"): button for button in tree.iter("button")
        }
        self.assertIn("action_buy_product", buttons)
        button = buttons["action_buy_product"]
        self.assertEqual(button.get("string"), "Mua hàng")
        self.assertEqual(
            button.get("invisible"),
            "menu_item_id or not product_id "
            "or product_stock_qty >= product_uom_qty",
        )

    def test_sale_tree_has_buy_button(self):
        arch = self.env.ref("set_top_menu.view_order_form_menu_item").arch_db
        self.assertIn('name="action_buy_product"', arch)
        self.assertIn('string="Mua hàng"', arch)
        self.assertIn("menu_item_id or not product_id", arch)
        self.assertIn("product_stock_qty", arch)

    def test_buy_product_ignores_uom_mismatch(self):
        gram = self.env.ref("uom.product_uom_gram")
        product = self._storable("SP gam mua", quantity=100.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách gam", "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": "DH-BUY-004",
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom": gram.id,
                "product_uom_qty": 500.0,
            }
        )
        action = line.action_buy_product()
        commands = action["context"]["default_order_line"]
        self.assertEqual(commands[0][2]["product_qty"], 400.0)

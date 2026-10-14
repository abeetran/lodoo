import xml.etree.ElementTree as ET

from odoo.tests.common import TransactionCase


class TestOrderTax(TransactionCase):
    def _tax(self, name="VAT 10%", amount=10.0):
        return self.env["account.tax"].create(
            {
                "name": name,
                "amount_type": "percent",
                "amount": amount,
                "type_tax_use": "sale",
                "invoice_repartition_line_ids": [
                    (0, 0, {"factor_percent": 100.0, "repartition_type": "base"}),
                    (0, 0, {"factor_percent": 100.0, "repartition_type": "tax"}),
                ],
                "refund_repartition_line_ids": [
                    (0, 0, {"factor_percent": 100.0, "repartition_type": "base"}),
                    (0, 0, {"factor_percent": 100.0, "repartition_type": "tax"}),
                ],
            }
        )

    def _order(self, reference="DH-TAX-001"):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )

    def _product(self, name="SP thuế"):
        template = self.env["product.template"].create({"name": name})
        return template.product_variant_id

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

    def test_order_tax_syncs_to_lines_and_totals(self):
        tax = self._tax()
        order = self._order()
        line_model = self.env["sale.order.line"]
        line_model.create(
            {
                "order_id": order.id,
                "product_id": self._product("SP thuế 1").id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        line_model.create(
            {
                "order_id": order.id,
                "product_id": self._product("SP thuế 2").id,
                "product_uom_qty": 1.0,
                "price_unit": 200.0,
            }
        )
        order.write({"catering_tax_id": tax.id})
        for line in order.order_line:
            self.assertEqual(line.tax_id, tax)
        self.assertEqual(order.amount_untaxed, 300.0)
        self.assertEqual(order.amount_tax, 30.0)
        self.assertEqual(order.amount_total, 330.0)

    def test_new_lines_inherit_order_tax(self):
        tax = self._tax()
        order = self._order("DH-TAX-002")
        order.write({"catering_tax_id": tax.id})
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self._product().id,
                "product_uom_qty": 2.0,
                "price_unit": 50.0,
            }
        )
        self.assertEqual(line.tax_id, tax)
        self.assertEqual(order.amount_tax, 10.0)

    def test_unset_tax_clears_lines(self):
        tax = self._tax()
        order = self._order("DH-TAX-003")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self._product().id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        order.write({"catering_tax_id": tax.id})
        self.assertEqual(order.amount_tax, 10.0)
        order.write({"catering_tax_id": False})
        self.assertFalse(order.order_line.tax_id)
        self.assertEqual(order.amount_tax, 0.0)
        self.assertEqual(order.amount_total, 100.0)

    def test_confirm_keeps_order_tax(self):
        tax = self._tax()
        order = self._order("DH-TAX-004")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self._product().id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        order.write({"catering_tax_id": tax.id})
        order.action_confirm()
        self.assertEqual(order.catering_state, "confirmed")
        self.assertEqual(order.order_line.tax_id, tax)
        self.assertEqual(order.amount_tax, 10.0)

    def test_no_order_tax_no_line_tax_despite_product_tax(self):
        product_tax = self._tax("VAT SP", 5.0)
        template = self.env["product.template"].create({"name": "SP có thuế"})
        template.taxes_id = product_tax
        order = self._order("DH-TAX-006")
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.product_id = template.product_variant_id
        self.assertFalse(line.tax_id)
        saved = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        self.assertFalse(saved.tax_id)
        self.assertEqual(order.amount_tax, 0.0)
        self.assertEqual(order.amount_total, 100.0)

    def test_product_tax_never_overrides_order_tax(self):
        product_tax = self._tax("VAT SP", 5.0)
        order_tax = self._tax("VAT đơn", 10.0)
        template = self.env["product.template"].create({"name": "SP lệch thuế"})
        template.taxes_id = product_tax
        order = self._order("DH-TAX-007")
        order.write({"catering_tax_id": order_tax.id})
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.product_id = template.product_variant_id
        self.assertEqual(line.tax_id, order_tax)
        saved = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        self.assertEqual(saved.tax_id, order_tax)
        self.assertEqual(order.amount_tax, 10.0)

    def test_menu_lines_get_order_tax(self):
        tax = self._tax()
        dish = self._dish("MON-TAX-001")
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        order = self._order("DH-TAX-005")
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": 2.0,
            }
        )
        order.write({"catering_tax_id": tax.id})
        self.assertEqual(line.tax_id, tax)

    def test_daily_form_tax_layout(self):
        view = self.env.ref("set_top_menu.view_daily_order_form")
        form = ET.fromstring(view.arch_db)
        self.assertTrue(
            form.find(".//field[@name='catering_tax_id']") is not None
        )
        footer = form.find(".//group[@class='oe_subtotal_footer oe_right']")
        rows = [
            (field.get("name"), field.get("string"), field.get("invisible"))
            for field in footer.iter("field")
        ]
        self.assertEqual(
            rows,
            [
                ("total_meals", "Tổng số lượng", "1"),
                ("amount_tax", "Tiền thuế", None),
                ("amount_total", "Tổng tiền", None),
            ],
        )

    def test_sale_form_has_tax_selector(self):
        arch = self.env.ref("set_top_menu.view_order_form_menu_item").arch_db
        self.assertIn('name="catering_tax_id"', arch)

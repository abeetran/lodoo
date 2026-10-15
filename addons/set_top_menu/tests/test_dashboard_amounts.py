from odoo.tests.common import TransactionCase


class TestDashboardAmounts(TransactionCase):
    def _partner(self, name):
        return self.env["res.partner"].create(
            {"name": name, "is_company": True}
        )

    def _priced_product(self, name, list_price):
        template = self.env["product.template"].create(
            {"name": name, "type": "product", "list_price": list_price}
        )
        return template.product_variant_id

    def _order(self, reference, partner, product, quantity, **extra):
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
                **extra,
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

    def _empty_outgoing(self):
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "outgoing")], limit=1
        )
        self.assertTrue(picking_type, "Thiếu loại lệnh outgoing")
        return self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "user_id": self.env.ref("base.user_admin").id,
                "location_id": self.env.ref("stock.stock_location_stock").id,
                "location_dest_id": self.env.ref(
                    "stock.stock_location_customers"
                ).id,
            }
        )

    def test_vnd_amount_equals_total(self):
        partner = self._partner("Khách TTB-001")
        product = self._priced_product("SP tiền tệ", 100.0)
        vnd = self.env.ref("base.VND")
        order = self._order(
            "DH-TTB-001", partner, product, 2.0, currency_id=vnd.id
        )
        self.assertEqual(order.amount_total, 200.0)
        self.assertEqual(order.catering_amount_vnd, 200.0)

    def test_foreign_currency_converts_to_vnd(self):
        partner = self._partner("Khách TTB-002")
        product = self._priced_product("SP ngoại tệ", 100.0)
        company = self.env.company
        vnd = self.env.ref("base.VND")
        usd = self.env.ref("base.USD")
        for currency, rate in ((usd, 1.0), (vnd, 25000.0)):
            self.env["res.currency.rate"].create(
                {
                    "name": "2020-01-01",
                    "rate": rate,
                    "currency_id": currency.id,
                    "company_id": company.id,
                }
            )
        order = self._order(
            "DH-TTB-002",
            partner,
            product,
            1.0,
            currency_id=usd.id,
        )
        self.assertEqual(order.amount_total, 100.0)
        expected = usd._convert(
            100.0,
            vnd,
            company,
            order.date_order,
        )
        self.assertEqual(order.catering_amount_vnd, expected)
        self.assertNotEqual(order.catering_amount_vnd, 100.0)

    def test_picking_sums_linked_orders_once(self):
        partner = self._partner("Khách TTB-003")
        vnd = self.env.ref("base.VND")
        first = self._order(
            "DH-TTB-003",
            partner,
            self._priced_product("SP pick A", 100.0),
            2.0,
            currency_id=vnd.id,
        )
        second = self._order(
            "DH-TTB-004",
            partner,
            self._priced_product("SP pick B", 150.0),
            2.0,
            currency_id=vnd.id,
        )
        self.assertEqual(first.catering_amount_vnd, 200.0)
        self.assertEqual(second.catering_amount_vnd, 300.0)
        picking = self._empty_outgoing()
        self.assertEqual(picking.catering_sale_amount, 0.0)
        picking.write({"sale_order_id": first.id})
        self.assertEqual(picking.catering_sale_amount, 200.0)
        picking.write({"sale_order_id": second.id})
        self.assertEqual(picking.catering_sale_amount, 300.0)

    def test_picking_counts_same_order_once(self):
        partner = self._partner("Khách TTB-005")
        product = self._priced_product("SP pick C", 100.0)
        vnd = self.env.ref("base.VND")
        order = self._order(
            "DH-TTB-005", partner, product, 2.0, currency_id=vnd.id
        )
        order.action_confirm()
        picking = order.picking_ids
        self.assertEqual(picking.sale_id, order)
        picking.write({"sale_order_id": order.id})
        self.assertEqual(picking.catering_sale_amount, 200.0)

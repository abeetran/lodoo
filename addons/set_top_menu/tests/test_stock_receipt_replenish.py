from odoo.tests.common import TransactionCase


class TestStockReceiptReplenish(TransactionCase):
    def _food(self, name, product_type="consu", source="foods", uom=None):
        vals = {
            "name": name,
            "type": product_type,
            "crall_food_source": source,
            "purchase_ok": True,
        }
        if uom:
            vals["uom_id"] = uom.id
            vals["uom_po_id"] = uom.id
        template = self.env["product.template"].create(vals)
        return template.product_variant_id

    def _purchase(self, product, quantity, uom=None):
        partner = self.env["res.partner"].create(
            {"name": "NCC %s" % product.name, "is_company": True}
        )
        order = self.env["purchase.order"].create(
            {"partner_id": partner.id}
        )
        self.env["purchase.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_qty": quantity,
                "product_uom": (uom or product.uom_po_id).id,
                "price_unit": 10.0,
            }
        )
        return order

    def _receive_all(self, order):
        order.button_confirm()
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)
        picking.move_ids.quantity = picking.move_ids.product_uom_qty
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        return picking

    def test_consu_receipt_replenishes_stock(self):
        product = self._food("Thịt nhập kho")
        self.assertEqual(product.qty_available, 0.0)
        self._receive_all(self._purchase(product, 2.0))
        self.assertEqual(product.qty_available, 2.0)

    def test_storable_receipt_not_doubled(self):
        product = self._food("Gạo nhập kho", product_type="product")
        self._receive_all(self._purchase(product, 2.0))
        self.assertEqual(product.qty_available, 2.0)

    def test_standard_food_receipt_replenishes(self):
        product = self._food("Món chuẩn nhập", source="standard")
        self._receive_all(self._purchase(product, 2.0))
        self.assertEqual(product.qty_available, 2.0)

    def test_receipt_converts_same_category_uom(self):
        kilo = self.env.ref("uom.product_uom_kgm")
        gram = self.env.ref("uom.product_uom_gram")
        product = self._food("Bột nhập kho", uom=kilo)
        self._receive_all(self._purchase(product, 500.0, uom=gram))
        self.assertEqual(product.qty_available, 0.5)

    def _sale_order(self, reference, product, quantity):
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
        order.action_confirm()
        return order

    def test_consu_lines_skip_stock_check_and_deduct(self):
        product = self._food("Rau tiêu hao")
        order = self._sale_order("DH-CONSU-001", product, 4.0)
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        self.assertEqual(product.qty_available, 0.0)

    def test_prepare_uses_latest_stock_after_receipt(self):
        product = self._food("Rau đơn hàng", product_type="product")
        order = self._sale_order("DH-STOCK-LIVE", product, 4.0)
        result = order.action_start_preparation()
        self.assertEqual(
            result["res_model"], "set_top_menu.order.shortage.wizard"
        )
        self._receive_all(self._purchase(product, 10.0))
        self.assertEqual(order.order_line.product_stock_qty, 10.0)
        order.action_start_preparation()
        self.assertEqual(order.catering_state, "in_production")
        self.assertEqual(product.qty_available, 6.0)

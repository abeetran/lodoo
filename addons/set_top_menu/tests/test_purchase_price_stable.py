from odoo.tests.common import TransactionCase


class TestPurchasePriceStable(TransactionCase):
    def test_qty_change_keeps_price_unit(self):
        supplier = self.env["res.partner"].create(
            {"name": "NCC giá ổn định", "is_company": True}
        )
        template = self.env["product.template"].create(
            {
                "name": "NVL giá ổn định",
                "type": "product",
                "purchase_ok": True,
            }
        )
        product = template.product_variant_id
        self.env["product.supplierinfo"].create(
            [
                {
                    "partner_id": supplier.id,
                    "product_tmpl_id": template.id,
                    "product_uom": product.uom_po_id.id,
                    "min_qty": 1.0,
                    "price": 100.0,
                },
                {
                    "partner_id": supplier.id,
                    "product_tmpl_id": template.id,
                    "product_uom": product.uom_po_id.id,
                    "min_qty": 10.0,
                    "price": 80.0,
                },
            ]
        )
        po = self.env["purchase.order"].create(
            {"partner_id": supplier.id}
        )
        line = self.env["purchase.order.line"].create(
            {
                "order_id": po.id,
                "product_id": product.id,
                "product_qty": 1.0,
                "product_uom": product.uom_po_id.id,
            }
        )
        self.assertEqual(line.price_unit, 100.0)
        line.write({"product_qty": 10.0})
        self.assertEqual(line.price_unit, 100.0)

    def test_product_change_reprices_line(self):
        supplier = self.env["res.partner"].create(
            {"name": "NCC đổi hàng", "is_company": True}
        )
        cheap = self.env["product.template"].create(
            {
                "name": "NVL rẻ",
                "type": "product",
                "purchase_ok": True,
            }
        )
        pricey = self.env["product.template"].create(
            {
                "name": "NVL đắt",
                "type": "product",
                "purchase_ok": True,
            }
        )
        for template, price in ((cheap, 50.0), (pricey, 200.0)):
            self.env["product.supplierinfo"].create(
                {
                    "partner_id": supplier.id,
                    "product_tmpl_id": template.id,
                    "product_uom": template.uom_po_id.id,
                    "min_qty": 1.0,
                    "price": price,
                }
            )
        po = self.env["purchase.order"].create(
            {"partner_id": supplier.id}
        )
        line = self.env["purchase.order.line"].create(
            {
                "order_id": po.id,
                "product_id": cheap.product_variant_id.id,
                "product_qty": 2.0,
                "product_uom": cheap.uom_po_id.id,
            }
        )
        self.assertEqual(line.price_unit, 50.0)
        line.write({"product_id": pricey.product_variant_id.id})
        self.assertEqual(line.price_unit, 200.0)

from odoo.tests.common import TransactionCase


class TestPurchaseUomIndependent(TransactionCase):
    def _supplier(self, name):
        return self.env["res.partner"].create(
            {"name": name, "is_company": True}
        )

    def _storable(self, name):
        template = self.env["product.template"].create(
            {
                "name": name,
                "type": "product",
                "purchase_ok": True,
            }
        )
        return template.product_variant_id

    def _independent_uom(self, name="Thùng độc lập", factor=0.5):
        category = self.env["uom.category"].create(
            {"name": "Đóng gói độc lập"}
        )
        self.env["uom.uom"].create(
            {
                "name": "Gói độc lập",
                "category_id": category.id,
                "uom_type": "reference",
                "factor": 1.0,
            }
        )
        return self.env["uom.uom"].create(
            {
                "name": name,
                "category_id": category.id,
                "uom_type": "bigger",
                "factor": factor,
            }
        )

    def test_cross_category_uom_keeps_raw_qty(self):
        supplier = self._supplier("NCC ĐVT độc lập")
        product = self._storable("NVL ĐVT độc lập")
        box = self._independent_uom()
        self.env["product.supplierinfo"].create(
            [
                {
                    "partner_id": supplier.id,
                    "product_tmpl_id": product.product_tmpl_id.id,
                    "product_uom": product.uom_po_id.id,
                    "min_qty": 1.0,
                    "price": 100.0,
                },
                {
                    "partner_id": supplier.id,
                    "product_tmpl_id": product.product_tmpl_id.id,
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
                "product_qty": 5.0,
                "product_uom": box.id,
            }
        )
        self.assertEqual(line.product_uom_qty, 5.0)
        # So lượng thô với min_qty: 5 < 10 nên vẫn nấc 100.
        self.assertEqual(line.price_unit, 100.0)
        self.assertEqual(line._get_gross_price_unit(), 100.0)
        line.write({"product_qty": 12.0})
        self.assertEqual(line.product_uom_qty, 12.0)
        self.assertEqual(line.price_unit, 100.0)

    def test_same_category_uom_still_converts(self):
        supplier = self._supplier("NCC cùng nhóm")
        product = self._storable("NVL cùng nhóm")
        gram = self.env.ref("uom.product_uom_gram")
        kilo = self.env.ref("uom.product_uom_kgm")
        product.product_tmpl_id.write({"uom_id": kilo.id})
        po = self.env["purchase.order"].create(
            {"partner_id": supplier.id}
        )
        line = self.env["purchase.order.line"].create(
            {
                "order_id": po.id,
                "product_id": product.id,
                "product_qty": 500.0,
                "product_uom": gram.id,
            }
        )
        self.assertEqual(line.product_uom_qty, 0.5)

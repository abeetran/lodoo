from odoo.tests.common import TransactionCase


class TestOrderDisplayReference(TransactionCase):
    def _order(self, reference):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )

    def test_display_name_prefers_reference(self):
        order = self._order("DH-DISP-001")
        self.assertEqual(order.display_name, "DH-DISP-001")

    def test_name_search_finds_by_reference(self):
        order = self._order("DH-SEARCH-001")
        found = self.env["sale.order"].name_search("DH-SEARCH-001")
        self.assertIn(order.id, [row[0] for row in found])
        found_by_name = self.env["sale.order"].name_search(order.name)
        self.assertIn(order.id, [row[0] for row in found_by_name])

    def test_procurement_origin_uses_reference(self):
        template = self.env["product.template"].create(
            {"name": "SP chứng từ gốc", "type": "product"}
        )
        product = template.product_variant_id
        order = self._order("DH-ORIG-001")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 2.0,
            }
        )
        order.action_confirm()
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(order.picking_ids.origin, "DH-ORIG-001")

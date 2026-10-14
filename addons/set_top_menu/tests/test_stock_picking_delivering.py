import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestStockPickingDelivering(TransactionCase):
    def _storable(self, name, quantity):
        template = self.env["product.template"].create(
            {"name": name, "type": "product"}
        )
        product = template.product_variant_id
        location = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"]._update_available_quantity(
            product, location, quantity
        )
        return product

    def _picking(self, code, product, quantity, src_xmlid, dest_location):
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", code)], limit=1
        )
        self.assertTrue(picking_type, "Thiếu loại lệnh %s" % code)
        src = self.env.ref(src_xmlid)
        admin = self.env.ref("base.user_admin")
        return self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "user_id": admin.id,
                "location_id": src.id,
                "location_dest_id": dest_location.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "name": product.name,
                            "product_id": product.id,
                            "product_uom_qty": quantity,
                            "product_uom": product.uom_id.id,
                            "location_id": src.id,
                            "location_dest_id": dest_location.id,
                        },
                    )
                ],
            }
        )

    def _outgoing(self, product, quantity=4.0):
        customers = self.env.ref("stock.stock_location_customers")
        return self._picking(
            "outgoing", product, quantity, "stock.stock_location_stock",
            customers,
        )

    def _internal_location(self):
        stock = self.env.ref("stock.stock_location_stock")
        return self.env["stock.location"].create(
            {
                "name": "Kệ trung chuyển test",
                "usage": "internal",
                "location_id": stock.location_id.id,
            }
        )

    def test_outgoing_validate_moves_to_delivering(self):
        product = self._storable("SP giao hàng", 10.0)
        picking = self._outgoing(product)
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        picking.button_validate()
        self.assertEqual(picking.state, "delivering")
        self.assertTrue(picking.is_delivering)
        self.assertEqual(picking.move_ids.state, "assigned")

    def test_delivering_validate_completes(self):
        product = self._storable("SP hoàn tất", 10.0)
        picking = self._outgoing(product)
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()
        picking.move_ids.quantity = 4.0
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_incoming_skips_delivering(self):
        product = self._storable("SP nhập kho", 10.0)
        suppliers = self.env.ref("stock.stock_location_suppliers")
        stock = self.env.ref("stock.stock_location_stock")
        picking = self.env["stock.picking.type"].search(
            [("code", "=", "incoming")], limit=1
        )
        self.assertTrue(picking)
        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": picking.id,
                "location_id": suppliers.id,
                "location_dest_id": stock.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "name": product.name,
                            "product_id": product.id,
                            "product_uom_qty": 4.0,
                            "product_uom": product.uom_id.id,
                            "location_id": suppliers.id,
                            "location_dest_id": stock.id,
                        },
                    )
                ],
            }
        )
        receipt.action_confirm()
        receipt.action_assign()
        self.assertEqual(receipt.state, "assigned")
        receipt.move_ids.quantity = 4.0
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertFalse(receipt.is_delivering)

    def test_internal_validate_moves_to_delivering(self):
        product = self._storable("SP chuyển kho", 10.0)
        picking = self._picking(
            "internal", product, 4.0, "stock.stock_location_stock",
            self._internal_location(),
        )
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        picking.button_validate()
        self.assertEqual(picking.state, "delivering")

    def test_cancel_from_delivering(self):
        product = self._storable("SP huỷ giao", 10.0)
        picking = self._outgoing(product)
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()
        picking.action_cancel()
        self.assertEqual(picking.state, "cancel")
        self.assertFalse(picking.is_delivering)

    def test_deliver_requires_responsible(self):
        product = self._storable("SP thiếu phụ trách", 10.0)
        picking = self._outgoing(product)
        picking.user_id = False
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        with self.assertRaises(UserError) as ctx:
            picking.button_validate()
        self.assertIn("Người phụ trách", str(ctx.exception))
        self.assertEqual(picking.state, "assigned")
        self.assertFalse(picking.is_delivering)

    def test_order_follows_picking_to_dispatched_delivered(self):
        product = self._storable("SP theo đơn", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách DH-FLOW-001", "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": "DH-FLOW-001",
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 4.0,
            }
        )
        order.action_confirm()
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        picking.user_id = self.env.ref("base.user_admin").id
        picking.button_validate()
        self.assertEqual(picking.state, "delivering")
        self.assertEqual(order.catering_state, "dispatched")
        picking.move_ids.quantity = 4.0
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(order.catering_state, "delivered")

    def test_combined_form_buttons(self):
        view = self.env.ref("stock.view_picking_form")
        arch = self.env["stock.picking"].fields_view_get(
            view_id=view.id, view_type="form"
        )["arch"]
        header = ET.fromstring(arch).find("header")
        validates = [
            node
            for node in header.findall("button")
            if node.get("name") == "button_validate"
        ]
        giao = [
            node for node in validates if node.get("string") == "Giao hàng"
        ]
        self.assertEqual(len(giao), 1)
        self.assertEqual(
            giao[0].get("invisible"),
            "state != 'assigned' or "
            "picking_type_code not in ('outgoing', 'internal')",
        )
        standards = [
            node for node in validates if node.get("string") == "Validate"
        ]
        self.assertEqual(len(standards), 2)
        invisibles = sorted(node.get("invisible") for node in standards)
        self.assertEqual(
            invisibles,
            [
                "state in ('draft', 'confirmed', 'done', 'cancel') or "
                "(state == 'assigned' and picking_type_code in "
                "('outgoing', 'internal'))",
                "state in "
                "('waiting', 'assigned', 'delivering', 'done', 'cancel')",
            ],
        )
        bars = [
            node
            for node in header.findall("field")
            if node.get("name") == "state"
            and node.get("widget") == "statusbar"
        ]
        others = [
            node
            for node in bars
            if node.get("invisible") == "picking_type_code == 'incoming'"
        ]
        self.assertEqual(len(others), 1)
        self.assertEqual(
            others[0].get("statusbar_visible"),
            "draft,confirmed,assigned,delivering,done",
        )

    def test_delivering_ordered_before_done(self):
        values = [
            pair[0]
            for pair in self.env["stock.picking"]._fields["state"].selection
        ]
        self.assertEqual(
            values,
            [
                "draft",
                "waiting",
                "confirmed",
                "assigned",
                "delivering",
                "done",
                "cancel",
            ],
        )

    def test_delivering_view_spec(self):
        arch = self.env.ref(
            "set_top_menu.view_picking_form_delivering"
        ).arch_db
        self.assertIn('string="Giao hàng"', arch)
        self.assertIn(
            "draft,confirmed,assigned,delivering,done<", arch
        )
        self.assertNotIn("done,cancel", arch)
        self.assertIn(
            "state not in "
            "('assigned', 'confirmed', 'draft', 'waiting', 'delivering')",
            arch,
        )
        search_arch = self.env.ref(
            "set_top_menu.view_picking_internal_search_delivering"
        ).arch_db
        self.assertIn("('state', 'in', ('assigned', 'delivering'))", search_arch)

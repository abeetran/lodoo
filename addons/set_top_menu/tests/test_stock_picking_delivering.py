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

    def _catering_order(
        self, reference, partner, shipping=None, state="in_production"
    ):
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )
        order.write(
            {
                "partner_shipping_id": (shipping or partner).id,
                "catering_state": state,
            }
        )
        return order

    def _order_line(self, order, product, quantity):
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": quantity,
            }
        )

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

    def test_order_domain_matches_preparing_and_contact(self):
        partner = self.env["res.partner"].create(
            {"name": "Khách DOM-001", "is_company": True}
        )
        other = self.env["res.partner"].create(
            {"name": "Khách DOM-002", "is_company": True}
        )
        by_customer = self._catering_order("DH-DOM-001", partner)
        by_shipping = self._catering_order("DH-DOM-002", other, shipping=partner)
        self._catering_order("DH-DOM-003", partner, state="confirmed")
        self._catering_order("DH-DOM-004", other)
        view = self.env.ref("stock.view_picking_form")
        arch = self.env["stock.picking"].fields_view_get(
            view_id=view.id, view_type="form"
        )["arch"]
        root = ET.fromstring(arch)
        node = root.find(".//field[@name='sale_order_id']")
        self.assertIsNotNone(node)
        self.assertIsNone(node.get("widget"))
        self.assertEqual(
            node.get("invisible"),
            "picking_type_code not in ('outgoing', 'internal')",
        )
        self.assertEqual(
            node.get("readonly"), "state in ('done', 'cancel')"
        )
        domain = eval(
            node.get("domain"),
            {"__builtins__": {}},
            {"partner_id": partner.id},
        )
        found = self.env["sale.order"].search(domain)
        self.assertCountEqual(found.ids, (by_customer | by_shipping).ids)
        origin = root.find(".//field[@name='origin']")
        self.assertEqual(origin.get("readonly"), "sale_order_id")

    def test_selecting_order_syncs_origin_and_moves(self):
        partner = self.env["res.partner"].create(
            {"name": "Khách SEL-001", "is_company": True}
        )
        product_a = self._storable("SP chọn A", 10.0)
        product_b = self._storable("SP chọn B", 10.0)
        manual_product = self._storable("SP chọn tay", 10.0)
        first = self._catering_order("DH-SEL-001", partner)
        self._order_line(first, product_a, 4.0)
        self._order_line(first, product_b, 2.0)
        second = self._catering_order("DH-SEL-002", partner)
        self._order_line(second, product_b, 5.0)
        picking = self._empty_outgoing()
        manual = self.env["stock.move"].create(
            {
                "name": manual_product.name,
                "product_id": manual_product.id,
                "product_uom_qty": 1.0,
                "product_uom": manual_product.uom_id.id,
                "picking_id": picking.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
            }
        )
        picking.write(
            {"partner_id": partner.id, "sale_order_id": first.id}
        )
        self.assertEqual(picking.origin, "DH-SEL-001")
        generated = picking.move_ids.filtered("catering_generated")
        self.assertEqual(len(generated), 2)
        by_product = {
            move.product_id.id: move.product_uom_qty for move in generated
        }
        self.assertEqual(
            by_product, {product_a.id: 4.0, product_b.id: 2.0}
        )
        self.assertCountEqual(
            generated.mapped("sale_line_id").ids, first.order_line.ids
        )
        self.assertIn(manual.id, picking.move_ids.ids)
        picking.write({"sale_order_id": second.id})
        self.assertEqual(picking.origin, "DH-SEL-002")
        generated = picking.move_ids.filtered("catering_generated")
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated.product_id, product_b)
        self.assertEqual(generated.product_uom_qty, 5.0)
        self.assertIn(manual.id, picking.move_ids.ids)
        picking.write({"sale_order_id": False})
        self.assertFalse(picking.origin)
        self.assertFalse(picking.move_ids.filtered("catering_generated"))
        self.assertIn(manual.id, picking.move_ids.ids)

    def test_onchange_selecting_order_syncs_origin_and_moves(self):
        partner = self.env["res.partner"].create(
            {"name": "Khách SEL-009", "is_company": True}
        )
        product_a = self._storable("SP onchange A", 10.0)
        product_b = self._storable("SP onchange B", 10.0)
        first = self._catering_order("DH-SEL-009", partner)
        self._order_line(first, product_a, 4.0)
        second = self._catering_order("DH-SEL-010", partner)
        self._order_line(second, product_b, 5.0)
        picking = self.env["stock.picking"].new(
            {
                "location_id": self.env.ref(
                    "stock.stock_location_stock"
                ).id,
                "location_dest_id": self.env.ref(
                    "stock.stock_location_customers"
                ).id,
            }
        )
        picking.sale_order_id = first
        result = picking._onchange_sale_order_id()
        self.assertIsNone(result)
        self.assertEqual(picking.origin, "DH-SEL-009")
        self.assertEqual(
            picking.move_ids.mapped("product_id"), product_a
        )
        self.assertEqual(picking.move_ids.product_uom_qty, 4.0)
        picking.sale_order_id = second
        picking._onchange_sale_order_id()
        self.assertEqual(picking.origin, "DH-SEL-010")
        self.assertEqual(
            picking.move_ids.mapped("product_id"), product_b
        )
        self.assertEqual(picking.move_ids.product_uom_qty, 5.0)

    def test_generated_moves_cover_only_remaining_qty(self):
        product_a = self._storable("SP còn lại A", 10.0)
        product_b = self._storable("SP còn lại B", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách REM-001", "is_company": True}
        )
        order = self._catering_order("DH-REM-001", partner, state="draft")
        line_a = self._order_line(order, product_a, 4.0)
        line_b = self._order_line(order, product_b, 4.0)
        order.action_confirm()
        auto = order.picking_ids
        self.assertEqual(len(auto), 1)
        auto.user_id = self.env.ref("base.user_admin").id
        auto.action_assign()
        self.assertEqual(auto.state, "assigned")
        auto.button_validate()
        auto.move_ids.filtered(
            lambda move: move.product_id == product_a
        ).quantity = 4.0
        auto.move_ids.filtered(
            lambda move: move.product_id == product_b
        ).quantity = 1.0
        result = auto.button_validate()
        wizard = self.env["stock.backorder.confirmation"].browse(
            result["res_id"]
        )
        wizard.process()
        self.assertEqual(auto.state, "done")
        self.assertEqual(line_a.qty_delivered, 4.0)
        self.assertEqual(line_b.qty_delivered, 1.0)
        order.write({"catering_state": "in_production"})
        picking = self._empty_outgoing()
        picking.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        generated = picking.move_ids.filtered("catering_generated")
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated.product_id, product_b)
        self.assertEqual(generated.product_uom_qty, 3.0)

    def test_selecting_same_order_skips_covered_lines(self):
        product = self._storable("SP trùng đơn", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách COV-001", "is_company": True}
        )
        order = self._catering_order("DH-COV-001", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_confirm()
        auto = order.picking_ids
        self.assertEqual(len(auto.move_ids), 1)
        auto.write({"sale_order_id": order.id})
        self.assertEqual(auto.origin, "DH-COV-001")
        self.assertEqual(len(auto.move_ids), 1)
        self.assertFalse(auto.move_ids.filtered("catering_generated"))

    def test_linked_order_follows_delivering_flow(self):
        product = self._storable("SP theo đơn tay", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách FLOW-002", "is_company": True}
        )
        order = self._catering_order("DH-FLOW-002", partner)
        self._order_line(order, product, 4.0)
        picking = self._empty_outgoing()
        picking.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        self.assertEqual(len(picking.move_ids), 1)
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        picking.button_validate()
        self.assertEqual(picking.state, "delivering")
        self.assertEqual(order.catering_state, "dispatched")
        picking.move_ids.quantity = 4.0
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(order.catering_state, "delivered")

    def test_cancel_picking_returns_preparation_stock(self):
        product = self._storable("SP hủy phiếu", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách CAN-001", "is_company": True}
        )
        order = self._catering_order("DH-CAN-001", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_confirm()
        order.action_start_preparation()
        self.assertEqual(product.qty_available, 6.0)
        self.assertTrue(order.stock_deducted)
        auto = order.picking_ids
        self.assertEqual(len(auto), 1)
        auto.action_cancel()
        self.assertEqual(auto.state, "cancel")
        self.assertEqual(order.catering_state, "in_production")
        self.assertEqual(product.qty_available, 10.0)
        self.assertFalse(order.stock_deducted)

    def test_unlink_picking_returns_preparation_stock_once(self):
        product = self._storable("SP xóa phiếu", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách DEL-001", "is_company": True}
        )
        order = self._catering_order("DH-DEL-001", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_confirm()
        order.action_start_preparation()
        self.assertEqual(product.qty_available, 6.0)
        manual = self._empty_outgoing()
        manual.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        manual.unlink()
        self.assertEqual(product.qty_available, 10.0)
        self.assertFalse(order.stock_deducted)
        auto = order.picking_ids
        auto.action_cancel()
        auto.unlink()
        self.assertEqual(product.qty_available, 10.0)

    def test_unlink_draft_order_returns_preparation_stock(self):
        product = self._storable("SP xóa đơn", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách DEL-002", "is_company": True}
        )
        order = self._catering_order("DH-DEL-002", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.with_context(skip_procurement=True).action_confirm()
        self.assertFalse(order.picking_ids)
        order.action_start_preparation()
        self.assertEqual(product.qty_available, 6.0)
        self.assertTrue(order.stock_deducted)
        order.action_draft()
        order_id = order.id
        order.unlink()
        self.assertFalse(
            self.env["sale.order"].browse(order_id).exists()
        )
        self.assertEqual(product.qty_available, 10.0)

    def test_delivered_order_blocks_preparation_return(self):
        product = self._storable("SP đã giao", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách DONE-001", "is_company": True}
        )
        order = self._catering_order("DH-DONE-001", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_confirm()
        order.action_start_preparation()
        auto = order.picking_ids
        auto.user_id = self.env.ref("base.user_admin").id
        auto.action_assign()
        auto.button_validate()
        auto.move_ids.quantity = 4.0
        auto.button_validate()
        self.assertEqual(auto.state, "done")
        self.assertEqual(order.catering_state, "delivered")
        manual = self._empty_outgoing()
        manual.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        manual.unlink()
        self.assertTrue(order.stock_deducted)
        self.assertEqual(product.qty_available, 2.0)

    def test_cancel_draft_order_keeps_stock(self):
        product = self._storable("SP hủy nháp", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách CAN-002", "is_company": True}
        )
        order = self._catering_order("DH-CAN-002", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_cancel()
        self.assertEqual(order.catering_state, "cancelled")
        self.assertEqual(product.qty_available, 10.0)

    def test_onchange_warns_when_nothing_generated(self):
        partner = self.env["res.partner"].create(
            {"name": "Khách WARN-001", "is_company": True}
        )
        service_template = self.env["product.template"].create(
            {"name": "DV giao hàng", "type": "service"}
        )
        service_order = self._catering_order("DH-WARN-001", partner)
        self._order_line(
            service_order, service_template.product_variant_id, 1.0
        )
        empty_order = self._catering_order("DH-WARN-002", partner)
        locations = {
            "location_id": self.env.ref(
                "stock.stock_location_stock"
            ).id,
            "location_dest_id": self.env.ref(
                "stock.stock_location_customers"
            ).id,
        }
        picking = self.env["stock.picking"].new(locations)
        picking.sale_order_id = service_order
        result = picking._onchange_sale_order_id()
        self.assertFalse(picking.move_ids)
        self.assertEqual(
            result["warning"]["title"], "Chưa sinh được dòng giao"
        )
        self.assertIn("dịch vụ", result["warning"]["message"])
        picking.sale_order_id = empty_order
        result = picking._onchange_sale_order_id()
        self.assertIn(
            "chưa có dòng chi tiết", result["warning"]["message"]
        )

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

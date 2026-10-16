import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestStockPickingDelivering(TransactionCase):
    def _storable(self, name, quantity):
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

    def _picking(self, code, product, quantity, src_xmlid, dest_location):
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", code)], limit=1
        )
        if not picking_type:
            template = self.env["stock.picking.type"].search(
                [("code", "=", "outgoing")], limit=1
            )
            self.assertTrue(template, "Thiếu loại lệnh outgoing")
            picking_type = template.copy(
                {"name": "Loại lệnh %s test" % code, "code": code}
            )
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
        self, reference, partner, shipping=None, state="draft"
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

    def _empty_incoming(self):
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "incoming")], limit=1
        )
        self.assertTrue(picking_type, "Thiếu loại lệnh incoming")
        return self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "user_id": self.env.ref("base.user_admin").id,
                "location_id": self.env.ref(
                    "stock.stock_location_suppliers"
                ).id,
                "location_dest_id": self.env.ref(
                    "stock.stock_location_stock"
                ).id,
            }
        )

    def _process_backorder(self, picking):
        result = picking.button_validate()
        self.assertEqual(
            result.get("res_model"), "stock.backorder.confirmation"
        )
        wizard = self.env["stock.backorder.confirmation"].with_context(
            button_validate_picking_ids=picking.ids
        ).create(
            {
                "pick_ids": [(6, 0, picking.ids)],
                "backorder_confirmation_line_ids": [
                    (
                        0,
                        0,
                        {"picking_id": picking.id, "to_backorder": True},
                    )
                ],
            }
        )
        wizard.process()

    def _purchase_order(self, partner, product, quantity):
        po = self.env["purchase.order"].create(
            {"partner_id": partner.id}
        )
        self.env["purchase.order.line"].create(
            {
                "order_id": po.id,
                "product_id": product.id,
                "product_qty": quantity,
                "product_uom": product.uom_po_id.id,
                "price_unit": 10.0,
            }
        )
        return po

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
        by_customer = self._catering_order(
            "DH-DOM-001", partner, state="in_production"
        )
        by_shipping = self._catering_order(
            "DH-DOM-002", other, shipping=partner, state="in_production"
        )
        self._catering_order("DH-DOM-003", partner, state="confirmed")
        self._catering_order("DH-DOM-004", other, state="in_production")
        view = self.env.ref("stock.view_picking_form")
        arch = self.env["stock.picking"].get_view(
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

    def test_delivered_with_remaining_selectable_for_transfer(self):
        product = self._storable("SP giao thiếu", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách SHORT-001", "is_company": True}
        )
        short = self._catering_order("DH-SHORT-001", partner, state="draft")
        self._order_line(short, product, 4.0)
        short.action_confirm()
        auto = short.picking_ids
        auto.user_id = self.env.ref("base.user_admin").id
        auto.action_assign()
        auto.button_validate()
        auto.move_ids.quantity = 1.0
        self._process_backorder(auto)
        self.assertEqual(short.order_line.qty_delivered, 1.0)
        short.write({"catering_state": "delivered"})
        self.assertTrue(short.catering_has_remaining)
        full = self._catering_order("DH-SHORT-002", partner, state="draft")
        self._order_line(full, product, 1.0)
        full.action_confirm()
        done = full.picking_ids
        done.user_id = self.env.ref("base.user_admin").id
        done.action_assign()
        done.button_validate()
        done.move_ids.quantity = 1.0
        done.button_validate()
        self.assertEqual(done.state, "done")
        self.assertEqual(full.catering_state, "delivered")
        self.assertFalse(full.catering_has_remaining)
        view = self.env.ref("stock.view_picking_form")
        arch = self.env["stock.picking"].get_view(
            view_id=view.id, view_type="form"
        )["arch"]
        node = ET.fromstring(arch).find(".//field[@name='sale_order_id']")
        domain = eval(
            node.get("domain"),
            {"__builtins__": {}},
            {"partner_id": partner.id},
        )
        other = self.env["res.partner"].create(
            {"name": "Khách SHORT-002", "is_company": True}
        )
        foreign = self._catering_order("DH-SHORT-003", other, state="draft")
        self._order_line(foreign, product, 2.0)
        foreign.action_confirm()
        foreign.write({"catering_state": "delivered"})
        self.assertTrue(foreign.catering_has_remaining)
        found = self.env["sale.order"].search(domain)
        self.assertIn(short.id, found.ids)
        self.assertNotIn(full.id, found.ids)
        # Đơn thiếu hàng nhưng khác khách thì không được lọt vào.
        self.assertNotIn(foreign.id, found.ids)
        transfer = self._empty_outgoing()
        transfer.write(
            {"partner_id": partner.id, "sale_order_id": short.id}
        )
        grid = transfer.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_uom_qty, 3.0)

    def test_purchase_domain_matches_short_and_vendor(self):
        product = self._storable("SP mua thiếu", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC PO-001", "is_company": True}
        )
        other = self.env["res.partner"].create(
            {"name": "NCC PO-002", "is_company": True}
        )
        short = self._purchase_order(vendor, product, 4.0)
        short.button_confirm()
        self.assertTrue(short.catering_has_remaining)
        full = self._purchase_order(vendor, product, 1.0)
        full.button_confirm()
        receipt = full.picking_ids
        self.assertEqual(len(receipt), 1)
        receipt.move_ids.quantity = 1.0
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertFalse(full.catering_has_remaining)
        foreign = self._purchase_order(other, product, 2.0)
        foreign.button_confirm()
        self.assertTrue(foreign.catering_has_remaining)
        draft = self._purchase_order(vendor, product, 2.0)
        view = self.env.ref("stock.view_picking_form")
        arch = self.env["stock.picking"].get_view(
            view_id=view.id, view_type="form"
        )["arch"]
        root = ET.fromstring(arch)
        node = root.find(".//field[@name='purchase_order_id']")
        self.assertIsNotNone(node)
        self.assertEqual(node.get("invisible"), "picking_type_code != 'incoming'")
        self.assertEqual(node.get("readonly"), "state in ('done', 'cancel')")
        domain = eval(
            node.get("domain"),
            {"__builtins__": {}},
            {"partner_id": vendor.id},
        )
        found = self.env["purchase.order"].search(domain)
        self.assertIn(short.id, found.ids)
        self.assertNotIn(full.id, found.ids)
        self.assertNotIn(foreign.id, found.ids)
        self.assertNotIn(draft.id, found.ids)

    def test_selecting_purchase_order_syncs_origin_and_moves(self):
        product = self._storable("SP mua chọn", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC PO-003", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 4.0)
        order.button_confirm()
        picking = self._empty_incoming()
        picking.write(
            {"partner_id": vendor.id, "purchase_order_id": order.id}
        )
        self.assertEqual(picking.origin, order.name)
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_id, product)
        self.assertEqual(grid.product_uom_qty, 4.0)
        self.assertEqual(grid.purchase_line_id, order.order_line)
        picking.write({"purchase_order_id": False})
        self.assertFalse(picking.origin)
        self.assertFalse(
            picking.move_ids_without_package.filtered("catering_generated")
        )

    def test_selecting_purchase_order_fills_vendor(self):
        product = self._storable("SP mua NCC", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC PO-005", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 4.0)
        order.button_confirm()
        picking = self._empty_incoming()
        self.assertFalse(picking.partner_id)
        picking.write({"purchase_order_id": order.id})
        self.assertEqual(picking.partner_id, vendor)
        self.assertEqual(picking.origin, order.name)
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)

    def test_purchase_partial_receipt_regenerates_remaining(self):
        product = self._storable("SP mua một phần", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC PO-004", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 4.0)
        order.button_confirm()
        first = self._empty_incoming()
        first.write(
            {"partner_id": vendor.id, "purchase_order_id": order.id}
        )
        first.action_confirm()
        first.action_assign()
        self.assertEqual(first.state, "assigned")
        first.move_ids.quantity = 1.0
        self._process_backorder(first)
        self.assertEqual(first.state, "done")
        self.assertEqual(order.order_line.qty_received, 1.0)
        self.assertTrue(order.catering_has_remaining)
        second = self._empty_incoming()
        second.write(
            {"partner_id": vendor.id, "purchase_order_id": order.id}
        )
        grid = second.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_uom_qty, 3.0)

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
        # Lưới form gắn move_ids_without_package: bản ghi chưa lưu mô
        # phỏng đúng những gì client thấy nên lưới phải có dòng ở đó.
        picking.sale_order_id = first
        result = picking._onchange_sale_order_id()
        self.assertIsNone(result)
        self.assertEqual(picking.origin, "DH-SEL-009")
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(grid.mapped("product_id"), product_a)
        self.assertEqual(grid.product_uom_qty, 4.0)
        picking.sale_order_id = second
        picking._onchange_sale_order_id()
        self.assertEqual(picking.origin, "DH-SEL-010")
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(grid.mapped("product_id"), product_b)
        self.assertEqual(grid.product_uom_qty, 5.0)

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
        self._process_backorder(auto)
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

    def test_partial_delivery_after_preparation_deducts_once(self):
        product = self._storable("SP giao một phần", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách PART-001", "is_company": True}
        )
        order = self._catering_order("DH-PART-001", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_confirm()
        order.action_start_preparation()
        self.assertEqual(product.qty_available, 6.0)
        auto = order.picking_ids
        auto.user_id = self.env.ref("base.user_admin").id
        auto.action_assign()
        auto.button_validate()
        self.assertEqual(auto.state, "delivering")
        auto.move_ids.quantity = 1.0
        self._process_backorder(auto)
        self.assertEqual(auto.state, "done")
        # Giữ chỗ đã hoàn trước khi lõi trừ thật: 10 - 1 đã giao.
        self.assertFalse(order.stock_deducted)
        self.assertEqual(product.qty_available, 9.0)
        backorder = self.env["stock.picking"].search(
            [("backorder_id", "=", auto.id)]
        )
        self.assertEqual(len(backorder), 1)
        backorder.user_id = self.env.ref("base.user_admin").id
        backorder.move_ids.quantity = 3.0
        backorder.button_validate()
        self.assertEqual(backorder.state, "delivering")
        backorder.button_validate()
        self.assertEqual(backorder.state, "done")
        self.assertEqual(product.qty_available, 6.0)

    def test_recreated_picking_regenerates_grid_after_delete(self):
        product = self._storable("SP tạo lại", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách RE-001", "is_company": True}
        )
        order = self._catering_order("DH-RE-001", partner)
        self._order_line(order, product, 4.0)
        first = self._empty_outgoing()
        first.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        self.assertEqual(
            len(
                first.move_ids_without_package.filtered(
                    "catering_generated"
                )
            ),
            1,
        )
        first.unlink()
        second = self._empty_outgoing()
        second.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        grid = second.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_id, product)
        self.assertEqual(grid.product_uom_qty, 4.0)

    def test_save_recovers_link_when_client_drops_it(self):
        product = self._storable("SP rớt liên kết", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách DROP-001", "is_company": True}
        )
        order = self._catering_order("DH-DROP-001", partner)
        self._order_line(order, product, 4.0)
        line = order.order_line
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "outgoing")], limit=1
        )
        stock = self.env.ref("stock.stock_location_stock")
        customers = self.env.ref("stock.stock_location_customers")
        # Mô phỏng client mất M2O lúc lưu nhưng còn dòng tự sinh.
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": partner.id,
                "location_id": stock.id,
                "location_dest_id": customers.id,
                "sale_order_id": False,
                "move_ids_without_package": [
                    (
                        0,
                        0,
                        {
                            "name": line.name,
                            "product_id": product.id,
                            "product_uom_qty": 4.0,
                            "product_uom": product.uom_id.id,
                            "location_id": stock.id,
                            "location_dest_id": customers.id,
                            "sale_line_id": line.id,
                            "catering_generated": True,
                        },
                    )
                ],
            }
        )
        self.assertEqual(picking.sale_order_id, order)
        self.assertEqual(picking.origin, "DH-DROP-001")
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_uom_qty, 4.0)
        self.assertEqual(grid.sale_line_id, line)

    def test_write_recovers_link_when_rows_kept(self):
        product = self._storable("SP rớt khi sửa", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách DROP-004", "is_company": True}
        )
        order = self._catering_order("DH-DROP-004", partner)
        self._order_line(order, product, 4.0)
        picking = self._empty_outgoing()
        picking.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        generated = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(generated), 1)
        # Client rớt M2O khi lưu bản sửa nhưng vẫn gửi dòng đang giữ.
        picking.write(
            {
                "sale_order_id": False,
                "move_ids_without_package": [(4, generated.id)],
            }
        )
        self.assertEqual(picking.sale_order_id, order)
        self.assertEqual(picking.origin, "DH-DROP-004")
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_uom_qty, 4.0)

    def test_write_recovers_purchase_link_when_rows_kept(self):
        product = self._storable("SP rớt mua khi sửa", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC DROP-004", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 4.0)
        order.button_confirm()
        picking = self._empty_incoming()
        picking.write(
            {"partner_id": vendor.id, "purchase_order_id": order.id}
        )
        generated = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(generated), 1)
        picking.write(
            {
                "purchase_order_id": False,
                "move_ids_without_package": [(4, generated.id)],
            }
        )
        self.assertEqual(picking.purchase_order_id, order)
        self.assertEqual(picking.origin, order.name)
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_uom_qty, 4.0)

    def test_create_with_link_regenerates_missing_rows(self):
        product = self._storable("SP mất dòng", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách DROP-003", "is_company": True}
        )
        order = self._catering_order("DH-DROP-003", partner)
        self._order_line(order, product, 4.0)
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "outgoing")], limit=1
        )
        # Client gửi liên kết nhưng mất dòng: sinh lại từ đơn.
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": partner.id,
                "location_id": self.env.ref(
                    "stock.stock_location_stock"
                ).id,
                "location_dest_id": self.env.ref(
                    "stock.stock_location_customers"
                ).id,
                "sale_order_id": order.id,
            }
        )
        self.assertEqual(picking.origin, "DH-DROP-003")
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_uom_qty, 4.0)

    def test_genuine_clear_still_wipes_grid(self):
        product = self._storable("SP xóa thật", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách DROP-002", "is_company": True}
        )
        order = self._catering_order("DH-DROP-002", partner)
        self._order_line(order, product, 4.0)
        picking = self._empty_outgoing()
        picking.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        generated = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(generated), 1)
        # Mô phỏng xóa thật trên UI: M2O rỗng kèm lệnh xóa dòng.
        picking.write(
            {
                "sale_order_id": False,
                "move_ids_without_package": [(2, generated.id)],
            }
        )
        self.assertFalse(picking.sale_order_id)
        self.assertFalse(picking.origin)
        self.assertFalse(
            picking.move_ids_without_package.filtered("catering_generated")
        )

    def test_save_recovers_purchase_link_when_client_drops_it(self):
        product = self._storable("SP rớt đơn mua", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC DROP-001", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 4.0)
        order.button_confirm()
        line = order.order_line
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "incoming")], limit=1
        )
        suppliers = self.env.ref("stock.stock_location_suppliers")
        stock = self.env.ref("stock.stock_location_stock")
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": vendor.id,
                "location_id": suppliers.id,
                "location_dest_id": stock.id,
                "purchase_order_id": False,
                "move_ids_without_package": [
                    (
                        0,
                        0,
                        {
                            "name": line.name,
                            "product_id": product.id,
                            "product_uom_qty": 4.0,
                            "product_uom": product.uom_id.id,
                            "location_id": suppliers.id,
                            "location_dest_id": stock.id,
                            "purchase_line_id": line.id,
                            "catering_generated": True,
                        },
                    )
                ],
            }
        )
        self.assertEqual(picking.purchase_order_id, order)
        self.assertEqual(picking.origin, order.name)
        grid = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_uom_qty, 4.0)
        self.assertEqual(grid.purchase_line_id, line)

    def test_genuine_purchase_clear_still_wipes_grid(self):
        product = self._storable("SP xóa đơn mua", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC DROP-002", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 4.0)
        order.button_confirm()
        picking = self._empty_incoming()
        picking.write(
            {"partner_id": vendor.id, "purchase_order_id": order.id}
        )
        generated = picking.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(generated), 1)
        picking.write(
            {
                "purchase_order_id": False,
                "move_ids_without_package": [(2, generated.id)],
            }
        )
        self.assertFalse(picking.purchase_order_id)
        self.assertFalse(picking.origin)
        self.assertFalse(
            picking.move_ids_without_package.filtered("catering_generated")
        )

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
        # Lõi Odoo chỉ cho xóa đơn nháp/hủy và chốt bếp chặn xóa dòng
        # đơn đang chuẩn bị: đưa cả hai trạng thái về nháp (mở chốt bếp
        # bằng context test), cờ giữ kho còn nguyên để unlink hoàn lại.
        order.with_context(hnck_sync=True).write(
            {"state": "draft", "catering_state": "draft"}
        )
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
        # Giao đủ: phần giữ chỗ lúc Chuẩn bị đã được hoàn trước khi
        # lõi trừ thật nên kho chỉ trừ đúng một lần (10 - 4).
        self.assertFalse(order.stock_deducted)
        self.assertEqual(product.qty_available, 6.0)
        manual = self._empty_outgoing()
        manual.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        manual.unlink()
        self.assertFalse(order.stock_deducted)
        self.assertEqual(product.qty_available, 6.0)

    def test_delivery_deducts_stock_only_once(self):
        product = self._storable("SP trừ một lần", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách ONCE-001", "is_company": True}
        )
        order = self._catering_order("DH-ONCE-001", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_confirm()
        order.action_start_preparation()
        self.assertEqual(product.qty_available, 6.0)
        auto = order.picking_ids
        auto.user_id = self.env.ref("base.user_admin").id
        auto.action_assign()
        auto.button_validate()
        self.assertEqual(auto.state, "delivering")
        # Đang giao chưa hoàn tất: phần giữ chỗ vẫn còn.
        self.assertTrue(order.stock_deducted)
        self.assertEqual(product.qty_available, 6.0)
        auto.move_ids.quantity = 4.0
        auto.button_validate()
        self.assertEqual(auto.state, "done")
        self.assertEqual(order.catering_state, "delivered")
        self.assertFalse(order.stock_deducted)
        self.assertEqual(product.qty_available, 6.0)
        self.assertGreaterEqual(product.qty_available, 0.0)

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

    def test_delivering_flow_skips_returned_orders(self):
        product = self._storable("SP bỏ qua trả", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách RET-010", "is_company": True}
        )
        order = self._catering_order("DH-RET-010", partner)
        self._order_line(order, product, 4.0)
        order.write({"catering_state": "delivered"})
        order.action_mark_returned()
        picking = self._empty_outgoing()
        picking.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        picking.button_validate()
        self.assertEqual(picking.state, "delivering")
        self.assertEqual(order.catering_state, "returned")

    def test_completed_delivery_skips_returned_orders(self):
        product = self._storable("SP xong vẫn trả", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách RET-011", "is_company": True}
        )
        order = self._catering_order("DH-RET-011", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_confirm()
        auto = order.picking_ids
        auto.user_id = self.env.ref("base.user_admin").id
        auto.action_assign()
        auto.button_validate()
        self.assertEqual(order.catering_state, "dispatched")
        order.write({"catering_state": "returned"})
        auto.move_ids.quantity = 4.0
        auto.button_validate()
        self.assertEqual(auto.state, "done")
        self.assertEqual(order.catering_state, "returned")

    def test_combined_form_buttons(self):
        view = self.env.ref("stock.view_picking_form")
        arch = self.env["stock.picking"].get_view(
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

    def _po_bodies(self, order):
        return " | ".join(order.message_ids.mapped("body") or [])

    def test_done_linked_receipt_logs_purchase_history(self):
        product = self._storable("SP sử nhập", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC PO-LOG-001", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 4.0)
        order.button_confirm()
        picking = self._empty_incoming()
        picking.write(
            {"partner_id": vendor.id, "purchase_order_id": order.id}
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 4.0
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        bodies = self._po_bodies(order)
        self.assertIn("Nhập bổ sung từ phiếu nhập", bodies)
        self.assertIn(picking.name, bodies)
        self.assertIn("SP sử nhập", bodies)
        self.assertIn("4", bodies)

    def test_partial_linked_receipt_logs_done_qty(self):
        product = self._storable("SP sử nhập một phần", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC PO-LOG-002", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 4.0)
        order.button_confirm()
        picking = self._empty_incoming()
        picking.write(
            {"partner_id": vendor.id, "purchase_order_id": order.id}
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 1.0
        self._process_backorder(picking)
        self.assertEqual(picking.state, "done")
        bodies = self._po_bodies(order)
        self.assertIn(picking.name, bodies)
        self.assertIn("SP sử nhập một phần: 1 ", bodies)

    def test_auto_receipt_logs_no_purchase_history(self):
        product = self._storable("SP tự nhập", 0.0)
        vendor = self.env["res.partner"].create(
            {"name": "NCC PO-LOG-003", "is_company": True}
        )
        order = self._purchase_order(vendor, product, 1.0)
        order.button_confirm()
        receipt = order.picking_ids
        self.assertFalse(receipt.purchase_order_id)
        receipt.move_ids.quantity = 1.0
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertNotIn(
            "Nhập bổ sung từ phiếu nhập", self._po_bodies(order)
        )

    def _sale_bodies(self, order):
        return " | ".join(order.message_ids.mapped("body") or [])

    def test_short_order_supplementary_delivery_logs_history(self):
        product = self._storable("SP giao bù", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách BU-001", "is_company": True}
        )
        order = self._catering_order("DH-BU-001", partner, state="draft")
        self._order_line(order, product, 4.0)
        order.action_confirm()
        auto = order.picking_ids
        auto.user_id = self.env.ref("base.user_admin").id
        auto.action_assign()
        auto.button_validate()
        auto.move_ids.quantity = 1.0
        self._process_backorder(auto)
        self.assertEqual(auto.state, "done")
        manual = self._empty_outgoing()
        manual.write(
            {"partner_id": partner.id, "sale_order_id": order.id}
        )
        grid = manual.move_ids_without_package.filtered(
            "catering_generated"
        )
        self.assertEqual(len(grid), 1)
        self.assertEqual(grid.product_uom_qty, 3.0)
        manual.user_id = self.env.ref("base.user_admin").id
        manual.action_confirm()
        manual.action_assign()
        self.assertEqual(manual.state, "assigned")
        manual.button_validate()
        self.assertEqual(manual.state, "delivering")
        manual.move_ids.quantity = 3.0
        manual.button_validate()
        self.assertEqual(manual.state, "done")
        bodies = self._sale_bodies(order)
        self.assertIn("Giao bổ sung từ phiếu giao", bodies)
        self.assertIn(manual.name, bodies)
        self.assertIn("SP giao bù: 3 ", bodies)

    def test_auto_delivery_logs_no_line_history(self):
        product = self._storable("SP giao thẳng", 10.0)
        partner = self.env["res.partner"].create(
            {"name": "Khách BU-002", "is_company": True}
        )
        order = self._catering_order("DH-BU-002", partner, state="draft")
        self._order_line(order, product, 2.0)
        order.action_confirm()
        auto = order.picking_ids
        self.assertFalse(auto.sale_order_id)
        auto.user_id = self.env.ref("base.user_admin").id
        auto.action_assign()
        auto.button_validate()
        auto.move_ids.quantity = 2.0
        auto.button_validate()
        self.assertEqual(auto.state, "done")
        self.assertNotIn("Giao bổ sung từ phiếu giao", self._sale_bodies(order))

    def test_grid_keeps_generated_flags_on_save(self):
        view = self.env.ref("stock.view_picking_form")
        arch = self.env["stock.picking"].get_view(
            view_id=view.id, view_type="form"
        )["arch"]
        tree = ET.fromstring(arch).find(
            ".//field[@name='move_ids_without_package']/tree"
        )
        self.assertIsNotNone(tree)
        by_name = {
            node.get("name"): node
            for node in tree.findall("field")
        }
        for name in ("catering_generated", "sale_line_id"):
            self.assertIn(name, by_name)
            self.assertEqual(by_name[name].get("force_save"), "1")

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

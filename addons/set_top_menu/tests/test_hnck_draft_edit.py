from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestHnckDraftEdit(TransactionCase):
    def _order_with_line(self, reference, hnck_order=True):
        school = self.env["res.partner"].create(
            {"name": "Trường %s" % reference, "is_company": True}
        )
        product = self.env["product.product"].search([], limit=1)
        order = (
            self.env["sale.order"]
            .with_context(hnck_sync=True)
            .create(
                {
                    "partner_id": school.id,
                    "catering_reference": reference,
                    "hnck_order": hnck_order,
                    "order_line": [
                        (
                            0,
                            0,
                            {"product_id": product.id, "product_uom_qty": 2},
                        )
                    ],
                }
            )
        )
        return order

    def test_hnck_draft_edits_price_and_note(self):
        order = self._order_with_line("DH-HNCK-DRAFT-001")
        self.assertEqual(order.catering_state, "draft")
        order.order_line.write(
            {"price_unit": 45000.0, "catering_note": "Giao trước 7h"}
        )
        self.assertEqual(order.order_line.price_unit, 45000.0)
        self.assertEqual(order.order_line.catering_note, "Giao trước 7h")

    def test_hnck_draft_blocks_other_line_fields(self):
        order = self._order_with_line("DH-HNCK-DRAFT-002")
        with self.assertRaises(UserError):
            order.order_line.write({"product_uom_qty": 5})
        with self.assertRaises(UserError):
            order.order_line.write(
                {"price_unit": 45000.0, "product_uom_qty": 5}
            )
        self.assertEqual(order.order_line.product_uom_qty, 2)

    def test_hnck_confirmed_blocks_price_and_note(self):
        order = self._order_with_line("DH-HNCK-CONF-001")
        order.write({"catering_state": "confirmed"})
        with self.assertRaises(UserError):
            order.order_line.write({"price_unit": 45000.0})
        with self.assertRaises(UserError):
            order.order_line.write({"catering_note": "Ghi chú muộn"})

    def test_manual_order_line_still_editable(self):
        order = self._order_with_line("DH-MANUAL-EDIT-001", hnck_order=False)
        order.order_line.write(
            {"price_unit": 30000.0, "catering_note": "Ghi chú tay"}
        )
        self.assertEqual(order.order_line.price_unit, 30000.0)
        self.assertEqual(order.order_line.catering_note, "Ghi chú tay")

    def test_daily_form_opens_price_note_for_hnck_draft(self):
        arch = self.env.ref("set_top_menu.view_daily_order_form").arch_db
        self.assertIn(
            'readonly="(hnck_order or catering_state not in '
            "('draft', 'confirmed')) and not (hnck_order and "
            'catering_state == \'draft\') and not hnck_price_editable"',
            arch,
        )
        self.assertIn(
            'invisible="parent.contract_id or parent.hnck_order"', arch
        )
        self.assertIn('readonly="parent.hnck_order"', arch)

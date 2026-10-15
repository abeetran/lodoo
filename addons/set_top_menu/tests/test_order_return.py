import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderReturn(TransactionCase):
    def _order(self, reference, state="delivered"):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )
        order.write({"catering_state": state})
        return order

    def test_returned_state_label(self):
        selection = dict(
            self.env["sale.order"]._fields["catering_state"].selection
        )
        self.assertEqual(selection["returned"], "Trả hàng")

    def test_mark_returned_from_delivered(self):
        order = self._order("DH-RET-001")
        before = len(order.message_ids)
        order.action_mark_returned()
        self.assertEqual(order.catering_state, "returned")
        self.assertEqual(len(order.message_ids), before + 1)
        self.assertIn("Trả hàng", order.message_ids[0].body)

    def test_mark_returned_requires_delivered(self):
        for state in (
            "draft",
            "confirmed",
            "in_production",
            "ready",
            "dispatched",
        ):
            order = self._order("DH-RET-%s" % state, state=state)
            with self.assertRaises(UserError):
                order.action_mark_returned()
            self.assertEqual(order.catering_state, state)

    def _return_button(self, xmlid):
        node = ET.fromstring(self.env.ref(xmlid).arch_db).find(
            ".//button[@name='action_mark_returned']"
        )
        self.assertIsNotNone(node, xmlid)
        return node

    def test_return_button_visible_only_for_delivered(self):
        for xmlid in (
            "set_top_menu.view_daily_order_form",
            "set_top_menu.view_order_form_menu_item",
        ):
            node = self._return_button(xmlid)
            for hnck, state, expected in (
                (False, "delivered", True),
                (False, "dispatched", False),
                (False, "draft", False),
                (True, "delivered", False),
            ):
                visible = not eval(
                    node.get("invisible") or "False",
                    {"__builtins__": {}},
                    {
                        "hnck_order": hnck,
                        "catering_state": state,
                        "id": 1,
                    },
                )
                self.assertEqual(
                    visible,
                    expected,
                    "%s hnck=%s state=%s" % (xmlid, hnck, state),
                )

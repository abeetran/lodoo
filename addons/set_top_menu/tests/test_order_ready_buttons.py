import xml.etree.ElementTree as ET

from odoo.tests.common import TransactionCase


class TestOrderReadyButtons(TransactionCase):
    TRANSITIONS = (
        "action_confirm",
        "action_start_preparation",
        "action_cancel_preparation",
        "action_cancel_order",
    )
    LATE_STATES = ("ready", "dispatched", "delivered")

    def _assert_no_transitions_visible(self, xmlid):
        view = self.env.ref(xmlid)
        root = ET.fromstring(view.arch_db)
        names = [
            node.get("name")
            for node in root.iter("button")
            if node.get("type") == "object"
        ]
        self.assertNotIn("action_dispatch", names)
        self.assertNotIn("action_deliver", names)
        for name in self.TRANSITIONS:
            node = root.find(".//button[@name='%s']" % name)
            if node is None:
                continue
            invisible = node.get("invisible") or "False"
            for state in self.LATE_STATES:
                visible = not eval(
                    invisible,
                    {"__builtins__": {}},
                    {
                        "catering_state": state,
                        "hnck_order": False,
                        "id": 1,
                    },
                )
                self.assertFalse(
                    visible, "%s shows %s at %s" % (xmlid, name, state)
                )

    def test_no_status_buttons_late_daily_form(self):
        self._assert_no_transitions_visible(
            "set_top_menu.view_daily_order_form"
        )

    def test_no_status_buttons_late_sale_form(self):
        self._assert_no_transitions_visible(
            "set_top_menu.view_order_form_menu_item"
        )

    def test_statusbar_lists_all_middle_stages(self):
        for xmlid in (
            "set_top_menu.view_daily_order_form",
            "set_top_menu.view_order_form_menu_item",
        ):
            arch = self.env.ref(xmlid).arch_db
            self.assertIn(
                "statusbar_visible=\"draft,confirmed,"
                "in_production,ready,dispatched,delivered\"",
                arch,
            )
            self.assertNotIn("confirmed.in_production", arch)

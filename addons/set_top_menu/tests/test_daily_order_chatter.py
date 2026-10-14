import xml.etree.ElementTree as ET

from odoo.tests.common import TransactionCase


class TestDailyOrderChatter(TransactionCase):
    def test_model_has_chatter_fields(self):
        model = self.env["sale.order"]
        self.assertIn("message_ids", model._fields)
        self.assertIn("activity_ids", model._fields)

    def test_form_has_chatter(self):
        view = self.env.ref("set_top_menu.view_daily_order_form")
        form = ET.fromstring(view.arch_db)
        chatter = form.find("./div[@class='oe_chatter']")
        self.assertIsNotNone(chatter)
        names = [
            field.get("name")
            for field in chatter
            if field.tag == "field"
        ]
        self.assertEqual(
            names,
            ["message_follower_ids", "activity_ids", "message_ids"],
        )

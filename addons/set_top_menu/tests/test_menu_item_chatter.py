import xml.etree.ElementTree as ET

from odoo.tests.common import TransactionCase


class TestMenuItemChatter(TransactionCase):
    def test_model_has_chatter_mixins(self):
        model = self.env["set_top_menu.menu.item"]
        self.assertIn("mail.thread", model._inherit or [])
        self.assertIn("mail.activity.mixin", model._inherit or [])
        self.assertIn("message_ids", model._fields)
        self.assertIn("activity_ids", model._fields)

    def test_form_has_chatter(self):
        view = self.env.ref("set_top_menu.view_menu_item_form")
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

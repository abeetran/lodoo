import xml.etree.ElementTree as ET

from odoo.tests.common import TransactionCase


class TestMaterialViews(TransactionCase):
    def test_material_action_shows_list_only(self):
        action = self.env.ref("set_top_menu.action_material_products")
        self.assertEqual(action.view_mode, "tree,form")

    def test_food_form_uom_override_arch(self):
        view = self.env.ref("set_top_menu.view_product_template_food_form")
        arch = ET.fromstring(view.arch_db)
        xpaths = [
            node
            for node in arch.iter("xpath")
            if "uom_id" in (node.get("expr") or "")
        ]
        by_position = {node.get("position"): node for node in xpaths}
        attr = by_position["attributes"].find("attribute[@name='invisible']")
        self.assertEqual(attr.text, "crall_food_source != 'standard'")
        node = by_position["after"].find("field[@name='uom_id']")
        self.assertEqual(node.get("string"), "Đơn vị tính")
        self.assertEqual(node.get("invisible"), "crall_food_source == 'standard'")
        self.assertIsNone(node.get("groups"))

    def test_food_form_uom_combined_arch(self):
        form = self.env.ref("product.product_template_form_view")
        nodes = ET.fromstring(form.arch).findall(".//field[@name='uom_id']")
        ours = [
            node
            for node in nodes
            if node.get("invisible") == "crall_food_source == 'standard'"
        ]
        self.assertEqual(len(ours), 1)
        self.assertIsNone(ours[0].get("groups"))
        gated = [
            node
            for node in nodes
            if "uom.group_uom" in (node.get("groups") or "")
            and node.get("invisible") == "crall_food_source != 'standard'"
        ]
        self.assertEqual(len(gated), 1)

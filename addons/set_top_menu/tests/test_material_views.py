from odoo.tests.common import TransactionCase


class TestMaterialViews(TransactionCase):
    def test_material_action_shows_list_only(self):
        action = self.env.ref("set_top_menu.action_material_products")
        self.assertEqual(action.view_mode, "tree,form")

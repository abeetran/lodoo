from odoo import fields
from odoo.tests.common import TransactionCase


class TestMenuItemEmployees(TransactionCase):
    def test_user_has_employee_code(self):
        field = self.env["res.users"]._fields.get("employee_code")
        self.assertIsNotNone(field, "Thiếu field employee_code.")
        self.assertIsInstance(field, fields.Char)
        user = self.env["res.users"].create(
            {"name": "NV Mon An", "login": "nv_mon_an",
             "employee_code": "NV-101"}
        )
        self.assertEqual(user.employee_code, "NV-101")
        user.write({"employee_code": "NV-102"})
        self.assertEqual(user.employee_code, "NV-102")

    def test_menu_item_employee_ids_is_multi_select_from_users(self):
        field = self.env["set_top_menu.menu.item"]._fields.get("employee_ids")
        self.assertIsNotNone(field, "Thiếu field employee_ids.")
        self.assertIsInstance(field, fields.Many2many)
        self.assertEqual(field.comodel_name, "res.users")

    def test_assign_multiple_employees_to_dish(self):
        user_model = self.env["res.users"]
        user1 = user_model.create(
            {"name": "NV Mon 1", "login": "nv_mon_1",
             "employee_code": "NV-201"}
        )
        user2 = user_model.create(
            {"name": "NV Mon 2", "login": "nv_mon_2",
             "employee_code": "NV-202"}
        )
        uom = self.env.ref("uom.product_uom_unit")
        dish = self.env["set_top_menu.menu.item"].create(
            {
                "name": "Món test",
                "item_code": "MON-TEST-001",
                "serving_size": 1.0,
                "serving_uom_id": uom.id,
                "employee_ids": [(6, 0, [user1.id, user2.id])],
            }
        )
        self.assertEqual(len(dish.employee_ids), 2)
        dish.write({"employee_ids": [(6, 0, [user2.id])]})
        self.assertEqual(dish.employee_ids.ids, [user2.id])

    def test_menu_item_form_view_has_employee_tab(self):
        view = self.env.ref("set_top_menu.view_menu_item_form")
        self.assertIn("employee_ids", view.arch_db)
        self.assertIn("Nhân viên thực hiện", view.arch_db)

    def test_users_form_view_has_employee_code(self):
        view = self.env.ref("set_top_menu.view_users_form_employee_code")
        self.assertIn("employee_code", view.arch_db)

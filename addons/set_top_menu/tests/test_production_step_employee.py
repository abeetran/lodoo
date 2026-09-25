from odoo import fields
from odoo.tests.common import TransactionCase


class TestProductionStepEmployees(TransactionCase):
    def test_employee_ids_is_multi_select_from_users(self):
        field = self.env["set_top_menu.production.step"]._fields.get(
            "employee_ids"
        )
        self.assertIsNotNone(field, "Thiếu field employee_ids.")
        self.assertIsInstance(field, fields.Many2many)
        self.assertEqual(field.comodel_name, "res.users")

    def test_assign_multiple_employees(self):
        user_model = self.env["res.users"]
        user1 = user_model.create(
            {"name": "NV Test 1", "login": "nv_test_1",
             "employee_code": "NV-001"}
        )
        user2 = user_model.create(
            {"name": "NV Test 2", "login": "nv_test_2",
             "employee_code": "NV-002"}
        )
        step = self.env["set_top_menu.production.step"].create(
            {
                "name": "Khâu test",
                "code": "KHAU-TEST-001",
                "employee_ids": [(6, 0, [user1.id, user2.id])],
            }
        )
        self.assertEqual(len(step.employee_ids), 2)
        step.write({"employee_ids": [(6, 0, [user1.id])]})
        self.assertEqual(step.employee_ids.ids, [user1.id])

    def test_step_form_view_has_employee_select(self):
        view = self.env.ref("set_top_menu.view_production_step_form")
        self.assertIn("employee_ids", view.arch_db)

    def test_create_popup_hides_employee_select(self):
        popup = self.env.ref("set_top_menu.view_production_step_form_create")
        self.assertEqual(popup.model, "set_top_menu.production.step")
        self.assertNotIn("employee_ids", popup.arch_db)
        for field_name in ("name", "code", "note"):
            self.assertIn(field_name, popup.arch_db)

    def test_create_popup_uses_dedicated_view(self):
        action = self.env["set_top_menu.production.step"].action_open_create_popup()
        popup = self.env.ref("set_top_menu.view_production_step_form_create")
        self.assertEqual(action["views"], [(popup.id, "form")])

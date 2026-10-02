import psycopg2
import xml.etree.ElementTree as ET

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestMenu(TransactionCase):
    def _age_group(self, name="Mầm non"):
        return self.env["set_top_menu.age.group"].create({"name": name})

    def _school(self, name="Trường Mầm non Hoa Sen", code="SCH-001"):
        return self.env["res.partner"].create(
            {"name": name, "school_code": code, "is_company": True}
        )

    def _menu_vals(self, **overrides):
        vals = {
            "name": "Thực đơn tuần 1",
            "code": "TD-001",
            "age_group_id": self._age_group().id,
            "weekday": "mon",
            "school_ids": [(6, 0, [self._school().id])],
            "note": "Ghi chú thực đơn",
        }
        vals.update(overrides)
        return vals

    def test_create_menu(self):
        menu = self.env["set_top_menu.menu"].create(self._menu_vals())
        self.assertEqual(menu.name, "Thực đơn tuần 1")
        self.assertEqual(menu.status, "applying")
        self.assertEqual(menu.audience_schedule_display, "Mầm non - Thứ 2")

    def test_code_must_be_unique(self):
        vals = self._menu_vals()
        self.env["set_top_menu.menu"].create(dict(vals))
        with self.assertRaises(psycopg2.IntegrityError):
            self.env["set_top_menu.menu"].create(dict(vals))

    def test_audience_schedule_display_combinations(self):
        model = self.env["set_top_menu.menu"]
        age = self._age_group()
        school = self._school()

        def vals(code, **overrides):
            base = {
                "name": "Thực đơn %s" % code,
                "code": code,
                "age_group_id": age.id,
                "weekday": "mon",
                "school_ids": [(6, 0, [school.id])],
            }
            base.update(overrides)
            return base

        full = model.create(vals("TD-FULL"))
        self.assertEqual(full.audience_schedule_display, "Mầm non - Thứ 2")
        # Bản ghi thiếu dùng new() vì nhóm tuổi/thứ đã bắt buộc khi tạo.
        age_only = model.new(vals("TD-AGE", weekday=False, school_ids=False))
        self.assertEqual(age_only.audience_schedule_display, "Mầm non")
        weekday_only = model.new(
            vals("TD-DAY", age_group_id=False, school_ids=False)
        )
        self.assertEqual(weekday_only.audience_schedule_display, "Thứ 2")
        bare = model.new({"name": "Thực đơn trống", "code": "TD-BARE"})
        self.assertFalse(bare.audience_schedule_display)

    def test_required_fields(self):
        fields = self.env["set_top_menu.menu"]._fields
        for field_name in ("code", "name", "age_group_id", "weekday"):
            self.assertTrue(
                fields[field_name].required,
                "Field %s phải bắt buộc." % field_name,
            )
        with self.assertRaises((UserError, ValidationError)):
            self.env["set_top_menu.menu"].create(
                {"name": "Thiếu trường", "code": "TD-REQ"}
            )

    def test_weekday_has_seven_options(self):
        selection = dict(
            self.env["set_top_menu.menu"]._fields["weekday"].selection
        )
        self.assertEqual(
            set(selection),
            {"mon", "tue", "wed", "thu", "fri", "sat", "sun"},
        )
        self.assertEqual(selection["mon"], "Thứ 2")
        self.assertEqual(selection["sun"], "Chủ nhật")

    def test_school_domain_lists_schools(self):
        field = self.env["set_top_menu.menu"]._fields["school_ids"]
        self.assertEqual(field.type, "many2many")
        self.assertEqual(field.comodel_name, "res.partner")
        self.assertIn(("school_code", "!=", False), field.domain)

    def test_create_and_update_multiple_schools(self):
        school1 = self._school("Trường Hoa Sen", "SCH-001")
        school2 = self._school("Trường Hoa Mai", "SCH-002")
        school3 = self._school("Trường Hoa Đào", "SCH-003")
        menu = self.env["set_top_menu.menu"].create(
            self._menu_vals(
                code="TD-MULTI",
                school_ids=[(6, 0, [school1.id, school2.id])],
            )
        )
        self.assertEqual(
            set(menu.school_ids.ids), {school1.id, school2.id}
        )
        menu.write({"school_ids": [(6, 0, [school2.id, school3.id])]})
        self.assertEqual(
            set(menu.school_ids.ids), {school2.id, school3.id}
        )

    def test_menus_action(self):
        action = self.env.ref("set_top_menu.action_menus")
        self.assertEqual(action.res_model, "set_top_menu.menu")
        self.assertEqual(action.view_mode, "tree,form")

    def test_menu_list_columns(self):
        view = self.env.ref("set_top_menu.view_menu_tree")
        for field_name in (
            "name",
            "code",
            "audience_schedule_display",
            "school_ids",
            "status",
            "note",
        ):
            self.assertIn(field_name, view.arch_db)

    def test_menu_form_inputs(self):
        view = self.env.ref("set_top_menu.view_menu_form")
        for field_name in (
            "name",
            "code",
            "age_group_id",
            "weekday",
            "status",
            "school_ids",
            "note",
        ):
            self.assertIn(field_name, view.arch_db)

    def test_menu_form_hides_active_field(self):
        view = self.env.ref("set_top_menu.view_menu_form")
        node = ET.fromstring(view.arch_db).find(".//field[@name='active']")
        self.assertIsNotNone(node)
        self.assertEqual(node.get("invisible"), "1")

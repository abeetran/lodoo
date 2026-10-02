from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestWarehouse(TransactionCase):
    def test_required_fields(self):
        fields = self.env["set_top_menu.warehouse"]._fields
        for field_name in ("name", "code", "address"):
            self.assertTrue(
                fields[field_name].required, "Field %s phải bắt buộc." % field_name
            )
        self.assertFalse(fields["area"].required)

    def test_create_warehouse(self):
        warehouse = self.env["set_top_menu.warehouse"].create(
            {
                "name": "Kho Hà Nội",
                "code": "KHO-001",
                "address": "123 Đường Láng, Hà Nội",
                "area": 500.0,
            }
        )
        self.assertEqual(warehouse.name, "Kho Hà Nội")
        self.assertEqual(warehouse.area, 500.0)

    def test_negative_area_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["set_top_menu.warehouse"].create(
                {
                    "name": "Kho lỗi",
                    "code": "KHO-ERR",
                    "address": "Địa chỉ test",
                    "area": -10.0,
                }
            )

    def test_create_popup_opens_dedicated_view(self):
        action = self.env["set_top_menu.warehouse"].action_open_create_popup()
        popup = self.env.ref("set_top_menu.view_warehouse_form_create")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["views"], [(popup.id, "form")])
        for field_name in ("name", "code", "address", "area"):
            self.assertIn(field_name, popup.arch_db)

    def test_warehouses_action_lists_warehouses(self):
        action = self.env.ref("set_top_menu.action_warehouses")
        self.assertEqual(action.res_model, "set_top_menu.warehouse")
        self.assertEqual(action.view_mode, "tree,form")

    def test_menu_right_below_data_sync(self):
        menu = self.env.ref("set_top_menu.menu_warehouses")
        data_sync = self.env.ref("crall_material.menu_crall_material_root")
        next_menu = self.env.ref("crall_material.menu_crall_standard_food")
        self.assertFalse(menu.parent_id, "QL kho phải là menu ngang hàng, không nằm trong Data Sync.")
        self.assertFalse(data_sync.parent_id)
        self.assertLess(data_sync.sequence, menu.sequence)
        self.assertLess(menu.sequence, next_menu.sequence)
        action = self.env.ref("set_top_menu.action_warehouses")
        self.assertEqual(menu.action._name, "ir.actions.act_window")
        self.assertEqual(menu.action.id, action.id)

    def test_action_builds_warehouse_payload(self):
        warehouse_model = self.env["set_top_menu.warehouse"]
        warehouse1 = warehouse_model.create(
            {
                "name": "Kho trung tâm Đống Đa",
                "code": "KHO01",
                "address": "45 Đường Tây Sơn, quận Đống Đa, Hà Nội",
                "area": 500.5,
            }
        )
        warehouse2 = warehouse_model.create(
            {
                "name": "Kho Cầu Giấy",
                "code": "kho02",
                "address": "12 Đường Cầu Giấy, Hà Nội",
            }
        )
        client_path = "odoo.addons.set_top_menu.models.warehouse.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.push_supplier_warehouses.return_value = {
                "ok": True
            }
            result = (warehouse1 + warehouse2).action_push_supplier_warehouses()
        mock_client.return_value.push_supplier_warehouses.assert_called_once_with(
            [
                {
                    "ma_kho": "KHO01",
                    "ten_kho": "Kho trung tâm Đống Đa",
                    "dia_chi": "45 Đường Tây Sơn, quận Đống Đa, Hà Nội",
                    "dien_tich": 500.5,
                },
                {
                    "ma_kho": "KHO02",
                    "ten_kho": "Kho Cầu Giấy",
                    "dia_chi": "12 Đường Cầu Giấy, Hà Nội",
                    "dien_tich": 0.0,
                },
            ]
        )
        self.assertEqual(result["tag"], "display_notification")

    def test_action_empty_raises(self):
        with self.assertRaises(UserError):
            self.env["set_top_menu.warehouse"].action_push_supplier_warehouses()

    def test_warehouse_tree_has_sync_button(self):
        view = self.env.ref("set_top_menu.view_warehouse_tree")
        self.assertIn("action_push_supplier_warehouses", view.arch_db)

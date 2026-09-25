from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestProductionProcessPush(TransactionCase):
    def _make_process(self):
        step_model = self.env["set_top_menu.production.step"]
        step1 = step_model.create({"name": "Sơ chế", "code": "SO_CHE"})
        step2 = step_model.create({"name": "Chế biến", "code": "CHE_BIEN"})
        step3 = step_model.create({"name": "Đóng gói", "code": "DONG_GOI"})
        return self.env["set_top_menu.production.process"].create(
            {
                "name": "Quy trình chế biến thịt heo",
                "code": "QT001",
                "product_type": "thuc_pham",
                "line_ids": [
                    (0, 0, {"step_id": step1.id, "sequence": 1}),
                    (0, 0, {"step_id": step2.id, "sequence": 2}),
                    (0, 0, {"step_id": step3.id, "sequence": 3}),
                ],
            }
        )

    def test_action_builds_process_payload(self):
        process = self._make_process()
        client_path = (
            "odoo.addons.set_top_menu.models.production_process.HnckClient"
        )
        with patch(client_path) as mock_client:
            mock_client.return_value.push_supplier_processes.return_value = {
                "ok": True
            }
            result = process.action_push_supplier_processes()
        mock_client.return_value.push_supplier_processes.assert_called_once_with(
            [
                {
                    "ma_quy_trinh": "QT001",
                    "ten_quy_trinh": "Quy trình chế biến thịt heo",
                    "loai_san_pham": "food",
                    "danh_sach_khau": [
                        {"ma_khau": "SO_CHE", "thu_tu": 1},
                        {"ma_khau": "CHE_BIEN", "thu_tu": 2},
                        {"ma_khau": "DONG_GOI", "thu_tu": 3},
                    ],
                }
            ]
        )
        self.assertEqual(result["tag"], "display_notification")

    def test_dish_product_type_maps_to_dish(self):
        step = self.env["set_top_menu.production.step"].create(
            {"name": "Sơ chế", "code": "SO_CHE"}
        )
        process = self.env["set_top_menu.production.process"].create(
            {
                "name": "Quy trình món ăn",
                "code": "QT002",
                "product_type": "thuc_an",
                "line_ids": [(0, 0, {"step_id": step.id, "sequence": 1})],
            }
        )
        payload = process._supplier_process_push_payload()
        self.assertEqual(payload["loai_san_pham"], "dish")
        self.assertEqual(
            payload["danh_sach_khau"], [{"ma_khau": "SO_CHE", "thu_tu": 1}]
        )

    def test_action_empty_raises(self):
        with self.assertRaises(UserError):
            self.env[
                "set_top_menu.production.process"
            ].action_push_supplier_processes()

    def test_process_tree_has_sync_button(self):
        view = self.env.ref("set_top_menu.view_production_process_tree")
        self.assertIn("action_push_supplier_processes", view.arch_db)

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestMaterialFoodPush(TransactionCase):
    def _standard_food(self):
        return self.env["product.template"].create(
            {
                "name": "Thịt nạc chuẩn",
                "crall_supplier_id": "969",
                "crall_supplier_code": "thit_nac",
                "crall_food_source": "standard",
            }
        )

    def test_action_builds_food_payload(self):
        old_process = self.env["set_top_menu.production.process"].create(
            {"name": "Quy trình cũ", "code": "qt001"}
        )
        new_process = self.env["set_top_menu.production.process"].create(
            {"name": "Quy trình mới", "code": "qt002"}
        )
        food = self.env["product.template"].create(
            {
                "name": "Thịt heo tươi",
                "default_code": "tp-thit-001",
                "barcode": "8938505970001",
                "crall_food_source": "foods",
                "crall_standard_food_id": self._standard_food().id,
                "crall_country": "Việt Nam",
                "process_ids": [(6, 0, [new_process.id, old_process.id])],
            }
        )
        client_path = (
            "odoo.addons.set_top_menu.models.product_template.HnckClient"
        )
        with patch(client_path) as mock_client:
            mock_client.return_value.push_supplier_foods.return_value = {
                "ok": True
            }
            result = food.action_push_supplier_foods()
        mock_client.return_value.push_supplier_foods.assert_called_once_with(
            [
                {
                    "ma_san_pham": "TP-THIT-001",
                    "ten_san_pham": "Thịt heo tươi",
                    "ma_loai_sp": "969",
                    "ma_thuc_pham_chuan": "thit_nac",
                    "gtin": "8938505970001",
                    "quoc_gia": "Việt Nam",
                    "ma_quy_trinh": "QT001",
                }
            ]
        )
        self.assertEqual(result["tag"], "display_notification")

    def test_action_empty_raises(self):
        with self.assertRaises(UserError):
            self.env["product.template"].action_push_supplier_foods()

    def test_material_tree_has_sync_button(self):
        view = self.env.ref("set_top_menu.view_material_product_tree")
        self.assertIn("action_push_supplier_foods", view.arch_db)

    def test_country_defaults_vietnam(self):
        food = self.env["product.template"].create(
            {"name": "Rau muống", "crall_food_source": "foods"}
        )
        self.assertEqual(food.crall_country, "Việt Nam")

    def test_material_form_has_country_field(self):
        view = self.env.ref("set_top_menu.view_product_template_food_form")
        self.assertIn("crall_country", view.arch_db)

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestProductionStepPush(TransactionCase):
    def test_action_builds_step_payload(self):
        step_model = self.env["set_top_menu.production.step"]
        step1 = step_model.create({"name": "Sơ chế", "code": "KHAU-1"})
        step2 = step_model.create({"name": "Chế biến", "code": "KHAU-2"})
        client_path = (
            "odoo.addons.set_top_menu.models.production_process.HnckClient"
        )
        with patch(client_path) as mock_client:
            mock_client.return_value.push_supplier_steps.return_value = {
                "ok": True
            }
            result = (step1 + step2).action_push_supplier_steps()
        mock_client.return_value.push_supplier_steps.assert_called_once_with(
            [
                {"ma_khau": "KHAU-1", "ten_khau": "Sơ chế"},
                {"ma_khau": "KHAU-2", "ten_khau": "Chế biến"},
            ]
        )
        self.assertEqual(result["tag"], "display_notification")

    def test_action_empty_raises(self):
        with self.assertRaises(UserError):
            self.env[
                "set_top_menu.production.step"
            ].action_push_supplier_steps()

    def test_step_tree_has_sync_button(self):
        view = self.env.ref("set_top_menu.view_production_step_tree")
        self.assertIn("action_push_supplier_steps", view.arch_db)

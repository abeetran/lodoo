import xml.etree.ElementTree as ET
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.crall_material.models.hnck_client import HnckClient


class TestUsersPush(TransactionCase):
    def _user(self, login, **extra):
        values = {
            "name": "Nguyễn Văn A",
            "login": login,
            "employee_code": "nv001",
            "job_position": "Chủ cơ sở",
            "contact_phone": "0912345678",
            "business_owner": True,
        }
        values.update(extra)
        return self.env["res.users"].create(values)

    def test_action_builds_user_payload(self):
        user = self._user(
            "nv_push_001",
            business_processor=True,
            business_transporter=True,
            transport_vehicle="Xe máy",
            transport_plate="29A-12345",
            health_cert_number="KSK-2026-001",
            health_cert_place="Bệnh viện Thanh Nhàn, Hà Nội",
            health_cert_date="2026-01-10",
            health_cert_expiry="2027-01-10",
            food_safety_cert_number="CHT-2026-001",
            food_safety_issue_date="2026-02-15",
            food_safety_issuer="Sở Y tế Hà Nội",
        )
        client_path = "odoo.addons.set_top_menu.models.res_users.HnckClient"
        with patch(client_path) as mock_client:
            mock_client.return_value.push_supplier_users.return_value = {
                "ok": True
            }
            result = user.action_push_supplier_users()
        mock_client.return_value.push_supplier_users.assert_called_once_with(
            [
                {
                    "ma_nhan_su": "NV001",
                    "ho_ten": "Nguyễn Văn A",
                    "vi_tri": "Chủ cơ sở",
                    "dien_thoai": "0912345678",
                    "la_chu_co_so": True,
                    "la_nguoi_che_bien": True,
                    "la_nguoi_giao_hang": True,
                    "trang_thai": True,
                    "phuong_tien": "Xe máy",
                    "bien_so": "29A-12345",
                    "giay_kham_suc_khoe": {
                        "so_giay": "KSK-2026-001",
                        "ngay_kham": "2026-01-10",
                        "ngay_het_han": "2027-01-10",
                        "noi_kham": "Bệnh viện Thanh Nhàn, Hà Nội",
                    },
                    "chung_nhan_tap_huan_attp": {
                        "so_chung_nhan": "CHT-2026-001",
                        "ngay_cap": "2026-02-15",
                        "co_quan_cap": "Sở Y tế Hà Nội",
                    },
                }
            ]
        )
        self.assertEqual(result["tag"], "display_notification")

    def test_owner_only_omits_conditional_sections(self):
        user = self._user("nv_push_002")
        payload = user._supplier_user_push_payload()
        self.assertTrue(payload["la_chu_co_so"])
        self.assertFalse(payload["la_nguoi_che_bien"])
        self.assertFalse(payload["la_nguoi_giao_hang"])
        self.assertNotIn("phuong_tien", payload)
        self.assertNotIn("bien_so", payload)
        self.assertNotIn("giay_kham_suc_khoe", payload)
        self.assertNotIn("chung_nhan_tap_huan_attp", payload)

    def test_action_empty_raises(self):
        with self.assertRaises(UserError):
            self.env["res.users"].action_push_supplier_users()

    def test_action_failure_shows_decoded_message(self):
        user = self._user("nv_push_003")
        client_path = "odoo.addons.set_top_menu.models.res_users.HnckClient"
        server_error = UserError(
            "Gọi HNCK merge thất bại: 400 Client Error\n"
            'Server trả về: {"message": "Biển số xe đã tồn tại"}\n'
            "X-Timestamp: 1\nX-Nonce: 2\nX-Signature: 3"
        )
        with patch(client_path) as mock_client:
            mock_client.return_value.push_supplier_users.side_effect = (
                server_error
            )
            result = user.action_push_supplier_users()
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "danger")
        self.assertEqual(
            result["params"]["message"], "Biển số xe đã tồn tại"
        )

    def test_client_empty_raises(self):
        with self.assertRaises(UserError):
            HnckClient(self.env).push_supplier_users([])

    def test_users_tree_has_sync_button(self):
        view = self.env.ref("set_top_menu.view_users_tree_sync")
        node = ET.fromstring(view.arch_db).find(
            ".//button[@name='action_push_supplier_users']"
        )
        self.assertIsNotNone(node)
        self.assertEqual(node.get("string"), "Đồng bộ")

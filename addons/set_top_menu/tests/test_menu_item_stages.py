import base64
import json
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


def _attachment(env, name, size):
    return env["ir.attachment"].create(
        {
            "name": name,
            "datas": base64.b64encode(b"x" * size).decode("ascii"),
        }
    )


def _set_base_url(env, url="https://odoo.vi-du.vn"):
    env["ir.config_parameter"].sudo().set_param("web.base.url", url)


def _dish_vals(env):
    uom = env.ref("uom.product_uom_unit")
    return {
        "name": "Món test khâu",
        "item_code": "MON-STAGE-001",
        "serving_size": 1.0,
        "serving_uom_id": uom.id,
    }


class TestMenuItemStages(TransactionCase):
    def test_stage_files_reject_more_than_3(self):
        files = [_attachment(self.env, "f%s.pdf" % i, 10) for i in range(4)]
        with self.assertRaises(ValidationError):
            self.env["set_top_menu.menu.item"].create(
                dict(
                    _dish_vals(self.env),
                    stage1_file_ids=[(6, 0, [f.id for f in files])],
                )
            )

    def test_stage_files_reject_oversize(self):
        big = _attachment(self.env, "big.pdf", 6 * 1024 * 1024)
        with self.assertRaises(ValidationError):
            self.env["set_top_menu.menu.item"].create(
                dict(
                    _dish_vals(self.env),
                    stage2_file_ids=[(6, 0, [big.id])],
                )
            )

    def test_stage_files_accept_valid(self):
        files = [
            _attachment(self.env, "ok0.pdf", 100),
            _attachment(self.env, "ok1.pdf", 100),
            _attachment(self.env, "anh.jpg", 100),
        ]
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                stage3_file_ids=[(6, 0, [f.id for f in files])],
            )
        )
        self.assertEqual(len(dish.stage3_file_ids), 3)

    def test_stage_files_reject_other_types(self):
        notes = _attachment(self.env, "ghi-chu.txt", 100)
        with self.assertRaises(ValidationError):
            self.env["set_top_menu.menu.item"].create(
                dict(
                    _dish_vals(self.env),
                    stage1_file_ids=[(6, 0, [notes.id])],
                )
            )

    def test_form_marks_stage_required_fields(self):
        view = self.env.ref("set_top_menu.view_menu_item_form")
        arch = view.arch_db
        for stage in ("stage1", "stage2", "stage3", "stage4"):
            for field in ("employee_ids", "info"):
                marker = 'name="%s_%s"' % (stage, field)
                self.assertIn(marker, arch)
                node = arch.split(marker)[1].split(">")[0]
                self.assertIn('required="1"', node)

    def test_stage_payload_maps_step2_tabs(self):
        _set_base_url(self.env)
        user_model = self.env["res.users"]
        user1 = user_model.create(
            {"name": "NV Khau 1", "login": "nv_khau_1",
             "employee_code": "NV001"}
        )
        user2 = user_model.create(
            {"name": "NV Khau 2", "login": "nv_khau_2",
             "employee_code": "NV002"}
        )
        site = self.env["crall.production.site"].create(
            {"name": "Cơ sở 1", "code": "CS001"}
        )
        doc1 = _attachment(self.env, "bien-ban-1.pdf", 100)
        doc2 = _attachment(self.env, "bien-ban-2.pdf", 100)
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MON-KHAU-001",
                stage1_employee_ids=[(6, 0, [user1.id, user2.id])],
                stage1_site_id=site.id,
                stage3_file_ids=[(6, 0, [doc1.id, doc2.id])],
            )
        )
        self.assertEqual(
            dish._supplier_dish_stage_payload(),
            [
                {
                    "ma_khau": "LAP_DON_HANG",
                    "thu_tu": 1,
                    "ma_co_so": "CS001",
                    "danh_sach_nguoi_thuc_hien": ["NV001", "NV002"],
                },
                {
                    "ma_khau": "NCC_SX_GIAO_HANG",
                    "thu_tu": 3,
                    "danh_sach_files": [
                        {
                            "ma_file": str(doc1.id),
                            "ten_file": "bien-ban-1.pdf",
                            "loai": "document",
                            "duong_dan": (
                                "https://odoo.vi-du.vn/web/content/%s/bien-ban-1.pdf"
                                % doc1.id
                            ),
                        },
                        {
                            "ma_file": str(doc2.id),
                            "ten_file": "bien-ban-2.pdf",
                            "loai": "document",
                            "duong_dan": (
                                "https://odoo.vi-du.vn/web/content/%s/bien-ban-2.pdf"
                                % doc2.id
                            ),
                        },
                    ],
                },
            ],
        )

    def test_stage_payload_falls_back_to_login_without_employee_code(self):
        user = self.env["res.users"].create(
            {"name": "NV No Code", "login": "nv_no_code"}
        )
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MON-KHAU-002",
                stage2_employee_ids=[(6, 0, [user.id])],
            )
        )
        payload = dish._supplier_dish_stage_payload()
        self.assertEqual(
            payload,
            [
                {
                    "ma_khau": "GUI_DON_NCC",
                    "thu_tu": 2,
                    "danh_sach_nguoi_thuc_hien": ["nv_no_code"],
                }
            ],
        )
        self.assertNotIn("danh_sach_files", payload[0])

    def test_stage_payload_empty_and_stored_fallback(self):
        dish = self.env["set_top_menu.menu.item"].create(
            dict(_dish_vals(self.env), item_code="MON-KHAU-003")
        )
        self.assertEqual(dish._supplier_dish_stage_payload(), [])
        stored = [{"ma_khau": "SO_CHE", "thu_tu": 1}]
        dish.write({"supplier_payload": {"danh_sach_khau": stored}})
        self.assertEqual(
            dish._supplier_dish_payload()["danh_sach_khau"], stored
        )

    def test_payload_uses_age_group_process_and_media(self):
        _set_base_url(self.env)
        age_group = self.env["set_top_menu.age.group"].create(
            {"name": "Mầm non", "supplier_age_id": 1}
        )
        process = self.env["set_top_menu.production.process"].create(
            {
                "name": "Quy trình món",
                "code": "QT-MON-01",
                "product_type": "thuc_an",
            }
        )
        template = self.env["product.template"].create(
            {"name": "Thịt heo", "default_code": "TP-THIT-001"}
        )
        variant = template.product_variant_id
        photo = _attachment(self.env, "mon-an.jpg", 100)
        doc = _attachment(self.env, "chung-nhan.pdf", 100)
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MA-001",
                name="Thịt heo sốt cà chua",
                description="<p>Món mặn phục vụ bữa trưa</p>",
                age_group_id=age_group.id,
                process_id=process.id,
                dish_image_ids=[(6, 0, [photo.id])],
                dish_document_ids=[(6, 0, [doc.id])],
            )
        )
        self.env["set_top_menu.menu.ingredient"].create(
            {
                "menu_item_id": dish.id,
                "product_id": variant.id,
                "quantity": 0.08,
                "uom_id": variant.uom_id.id,
            }
        )
        payload = dish._supplier_dish_payload()
        self.assertEqual(payload["ma_mon_an"], "MA-001")
        self.assertEqual(payload["ten_mon_an"], "Thịt heo sốt cà chua")
        self.assertEqual(payload["nhom_tuoi_id"], 1)
        self.assertEqual(payload["mo_ta"], "Món mặn phục vụ bữa trưa")
        self.assertEqual(payload["ma_quy_trinh"], "QT-MON-01")
        self.assertEqual(
            payload["danh_sach_nguyen_lieu"],
            [
                {
                    "ma_nguyen_lieu": "TP-THIT-001",
                    "dinh_luong": 0.08,
                    "don_vi_tinh_id": variant.uom_id.id,
                }
            ],
        )
        self.assertEqual(
            payload["danh_sach_anh"],
            [
                {
                    "ma_file": str(photo.id),
                    "ten_file": "mon-an.jpg",
                    "ten_anh": "mon-an.jpg",
                    "loai": "image",
                    "duong_dan": (
                        "https://odoo.vi-du.vn/web/content/%s/mon-an.jpg"
                        % photo.id
                    ),
                },
                {
                    "ma_file": str(doc.id),
                    "ten_file": "chung-nhan.pdf",
                    "ten_anh": "chung-nhan.pdf",
                    "loai": "document",
                    "duong_dan": (
                        "https://odoo.vi-du.vn/web/content/%s/chung-nhan.pdf"
                        % doc.id
                    ),
                },
            ],
        )

    def test_file_link_prefers_request_host(self):
        _set_base_url(self.env, "https://configured.vn")
        photo = _attachment(self.env, "mon-an.jpg", 100)
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MON-LINK-002",
                dish_image_ids=[(6, 0, [photo.id])],
            )
        )
        fake_request = SimpleNamespace(
            httprequest=SimpleNamespace(host_url="https://app.server.vn/")
        )
        with patch("odoo.http.request", fake_request):
            link = dish._supplier_file_duong_dan(photo)
        self.assertEqual(
            link, "https://app.server.vn/web/content/%s/mon-an.jpg" % photo.id
        )

    def test_file_link_quotes_filename(self):
        _set_base_url(self.env, "https://odoo.vi-du.vn")
        photo = _attachment(self.env, "ảnh chế biến.jpg", 100)
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MON-LINK-003",
                dish_image_ids=[(6, 0, [photo.id])],
            )
        )
        [entry] = dish._supplier_dish_media_payload()
        self.assertTrue(
            entry["duong_dan"].endswith(
                "/web/content/%s/%s" % (photo.id, quote("ảnh chế biến.jpg"))
            ),
            entry["duong_dan"],
        )
        self.assertNotIn(" ", entry["duong_dan"])
        self.assertEqual(entry["ten_anh"], "ảnh chế biến.jpg")

    def test_file_link_falls_back_to_relative_without_base_url(self):
        _set_base_url(self.env, "")
        photo = _attachment(self.env, "mon-an.jpg", 100)
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MON-LINK-001",
                dish_image_ids=[(6, 0, [photo.id])],
            )
        )
        self.assertEqual(
            dish._supplier_dish_media_payload(),
            [
                {
                    "ma_file": str(photo.id),
                    "ten_file": "mon-an.jpg",
                    "ten_anh": "mon-an.jpg",
                    "loai": "image",
                    "duong_dan": "/web/content/%s/mon-an.jpg" % photo.id,
                }
            ],
        )

    def test_payload_falls_back_to_supplier_codes(self):
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MON-FB-001",
                supplier_age_group_id=2,
                supplier_procedure_code="NCC-QT-9",
            )
        )
        payload = dish._supplier_dish_payload()
        self.assertEqual(payload["nhom_tuoi_id"], 2)
        self.assertEqual(payload["ma_quy_trinh"], "NCC-QT-9")
        self.assertEqual(payload["danh_sach_anh"], [])

    def test_form_has_two_steps_and_media_tab(self):
        view = self.env.ref("set_top_menu.view_menu_item_form")
        arch = view.arch_db
        self.assertIn("Bước 1", arch)
        self.assertIn("Bước 2", arch)
        self.assertIn("dish_image_ids", arch)
        self.assertIn("dish_document_ids", arch)
        for label in (
            "Khâu 1",
            "Khâu 2",
            "Khâu 3",
            "Khâu 4",
            "stage1_site_id",
            "stage1_address",
            "stage4_file_ids",
        ):
            self.assertIn(label, arch)


class TestDishPushConfirmWizard(TransactionCase):
    def test_sync_opens_confirm_popup_without_sending(self):
        dish = self.env["set_top_menu.menu.item"].create(
            dict(_dish_vals(self.env), item_code="MON-POP-001")
        )
        client_path = (
            "odoo.addons.set_top_menu.models.menu_item.HnckClient"
        )
        with patch(client_path) as mock_client:
            action = dish.action_push_supplier_dishes()
            mock_client.return_value.push_supplier_dishes.assert_not_called()
        self.assertEqual(
            action["res_model"], "set_top_menu.dish.push.wizard"
        )
        self.assertEqual(action["target"], "new")
        wizard = self.env["set_top_menu.dish.push.wizard"].browse(
            action["res_id"]
        )
        self.assertTrue(wizard.exists())
        self.assertEqual(wizard.state, "draft")
        body = json.loads(wizard.payload_text)
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["ma_mon_an"], "MON-POP-001")
        for key in (
            "ten_mon_an",
            "nhom_tuoi_id",
            "mo_ta",
            "ma_quy_trinh",
            "danh_sach_nguyen_lieu",
            "danh_sach_khau",
            "danh_sach_anh",
        ):
            self.assertIn(key, body[0])

    def test_confirm_sends_approved_payload(self):
        payloads = [{"ma_mon_an": "MA-001", "ten_mon_an": "Món duyệt"}]
        wizard = self.env["set_top_menu.dish.push.wizard"].create(
            {
                "name": "Đồng bộ 1 món ăn",
                "payload_text": json.dumps(payloads),
            }
        )
        client_path = (
            "odoo.addons.set_top_menu.models.menu_item.HnckClient"
        )
        with patch(client_path) as mock_client:
            mock_client.return_value.push_supplier_dishes.return_value = {
                "ok": True
            }
            action = wizard.action_confirm_push()
        mock_client.return_value.push_supplier_dishes.assert_called_once_with(
            payloads
        )
        self.assertEqual(wizard.state, "done")
        self.assertIn("ok", wizard.result_text)
        self.assertEqual(action["res_id"], wizard.id)
        self.assertEqual(action["target"], "new")

    def test_confirm_empty_payload_raises(self):
        wizard = self.env["set_top_menu.dish.push.wizard"].create(
            {"name": "Rỗng", "payload_text": "[]"}
        )
        with self.assertRaises(UserError):
            wizard.action_confirm_push()

    def test_wizard_form_view_has_confirm_button(self):
        view = self.env.ref("set_top_menu.view_dish_push_wizard_form")
        self.assertIn("payload_text", view.arch_db)
        self.assertIn("result_text", view.arch_db)
        self.assertIn("action_confirm_push", view.arch_db)

import base64
import os
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_path
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


def _make_step(env, name, code):
    return env["set_top_menu.production.step"].create(
        {"name": name, "code": code}
    )


def _make_process(env, code="QT-LINE-001"):
    step_model = env["set_top_menu.production.step"]
    steps = [
        step_model.create({"name": name, "code": code_})
        for name, code_ in (
            ("Sơ chế", "SO_CHE"),
            ("Chế biến", "CHE_BIEN"),
            ("Đóng gói", "DONG_GOI"),
        )
    ]
    return env["set_top_menu.production.process"].create(
        {
            "name": "Quy trình dòng khâu",
            "code": code,
            "product_type": "thuc_an",
            "line_ids": [
                (0, 0, {"step_id": step.id, "sequence": (i + 1) * 10})
                for i, step in enumerate(steps)
            ],
        }
    )


class TestMenuItemStages(TransactionCase):
    def _user(self, tag, code="NV001"):
        return self.env["res.users"].create(
            {
                "name": "NV %s" % tag,
                "login": "nv_%s" % tag,
                "employee_code": code,
            }
        )

    def _dish(self, code="MON-STAGE-001"):
        return self.env["set_top_menu.menu.item"].create(
            dict(_dish_vals(self.env), item_code=code)
        )

    def _line(self, dish, step, sequence=1, **kwargs):
        vals = {
            "menu_item_id": dish.id,
            "step_id": step.id,
            "sequence": sequence,
            "employee_ids": [(6, 0, [self._user("l%s" % sequence).id])],
            "info": "Thông tin khâu",
        }
        vals.update(kwargs)
        return self.env["set_top_menu.menu.item.stage"].create(vals)

    def test_stage_files_reject_more_than_3(self):
        step = _make_step(self.env, "Sơ chế", "SO_CHE_F1")
        dish = self._dish("MON-FILE-001")
        files = [_attachment(self.env, "f%s.pdf" % i, 10) for i in range(4)]
        with self.assertRaises(ValidationError):
            self._line(
                dish, step,
                file_ids=[(6, 0, [f.id for f in files])],
            )

    def test_stage_files_reject_total_over_5mb(self):
        step = _make_step(self.env, "Sơ chế", "SO_CHE_F2")
        dish = self._dish("MON-FILE-002")
        files = [
            _attachment(self.env, "p%s.pdf" % i, 2 * 1024 * 1024)
            for i in range(3)
        ]
        with self.assertRaises(ValidationError):
            self._line(dish, step, file_ids=[(6, 0, [f.id for f in files])])

    def test_stage_files_accept_total_within_5mb(self):
        step = _make_step(self.env, "Sơ chế", "SO_CHE_F3")
        dish = self._dish("MON-FILE-003")
        files = [
            _attachment(self.env, "ok0.pdf", 2 * 1024 * 1024),
            _attachment(self.env, "ok1.pdf", 2 * 1024 * 1024),
            _attachment(self.env, "anh.jpg", 100),
        ]
        line = self._line(
            dish, step, file_ids=[(6, 0, [f.id for f in files])]
        )
        self.assertEqual(len(line.file_ids), 3)

    def test_stage_files_reject_other_types(self):
        step = _make_step(self.env, "Sơ chế", "SO_CHE_F4")
        dish = self._dish("MON-FILE-004")
        notes = _attachment(self.env, "ghi-chu.txt", 100)
        with self.assertRaises(ValidationError):
            self._line(dish, step, file_ids=[(6, 0, [notes.id])])

    def test_stage_line_requires_employee_and_info(self):
        step = _make_step(self.env, "Sơ chế", "SO_CHE_R1")
        dish = self._dish("MON-REQ-001")
        with self.assertRaises((UserError, ValidationError)):
            self.env["set_top_menu.menu.item.stage"].create(
                {
                    "menu_item_id": dish.id,
                    "step_id": step.id,
                    "sequence": 1,
                    "info": "Thiếu nhân viên",
                }
            )
        with self.assertRaises((UserError, ValidationError)):
            self.env["set_top_menu.menu.item.stage"].create(
                {
                    "menu_item_id": dish.id,
                    "step_id": step.id,
                    "sequence": 1,
                    "employee_ids": [(6, 0, [self._user("req").id])],
                }
            )

    def test_onchange_builds_stage_lines_from_process(self):
        process = _make_process(self.env)
        dish = self.env["set_top_menu.menu.item"].new(
            dict(_dish_vals(self.env), item_code="MON-OC-001")
        )
        dish.process_id = process
        dish._onchange_process_id()
        self.assertEqual(
            [(line.sequence, line.step_id.name) for line in dish.stage_line_ids],
            [(1, "Sơ chế"), (2, "Chế biến"), (3, "Đóng gói")],
        )
        dish.process_id = False
        dish._onchange_process_id()
        self.assertFalse(dish.stage_line_ids)

    def test_stage_payload_uses_process_step_codes(self):
        _set_base_url(self.env)
        user1 = self._user("khau_1", "NV001")
        user2 = self._user("khau_2", "NV002")
        site = self.env["crall.production.site"].create(
            {"name": "Cơ sở 1", "code": "CS001"}
        )
        doc1 = _attachment(self.env, "bien-ban-1.pdf", 100)
        doc2 = _attachment(self.env, "bien-ban-2.pdf", 100)
        process = _make_process(self.env, code="QT-KHAU-001")
        steps = {
            line.step_id.code: line.step_id
            for line in process.line_ids
        }
        user3 = self._user("khau_3", "NV003")
        dish = self._dish("MON-KHAU-001")
        self._line(
            dish, steps["SO_CHE"], sequence=1,
            employee_ids=[(6, 0, [user1.id, user2.id])],
            site_id=site.id,
        )
        self._line(
            dish, steps["DONG_GOI"], sequence=3,
            employee_ids=[(6, 0, [user3.id])],
            file_ids=[(6, 0, [doc1.id, doc2.id])],
        )
        self.assertEqual(
            dish._supplier_dish_stage_payload(),
            [
                {
                    "ma_khau": "SO_CHE",
                    "thu_tu": 1,
                    "ghi_chu": "Thông tin khâu",
                    "dia_chi": "",
                    "ma_co_so": "CS001",
                    "danh_sach_nguoi_thuc_hien": ["NV001", "NV002"],
                },
                {
                    "ma_khau": "DONG_GOI",
                    "thu_tu": 3,
                    "ghi_chu": "Thông tin khâu",
                    "dia_chi": "",
                    "danh_sach_nguoi_thuc_hien": ["NV003"],
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

    def test_stage_payload_omits_user_without_employee_code(self):
        step = _make_step(self.env, "Sơ chế", "SO_CHE_L1")
        user = self.env["res.users"].create(
            {"name": "NV No Code", "login": "nv_no_code"}
        )
        dish = self._dish("MON-KHAU-002")
        self._line(
            dish, step, sequence=2, employee_ids=[(6, 0, [user.id])]
        )
        payload = dish._supplier_dish_stage_payload()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["ma_khau"], "SO_CHE_L1")
        self.assertEqual(payload[0]["thu_tu"], 2)
        self.assertNotIn("danh_sach_nguoi_thuc_hien", payload[0])
        self.assertNotIn("danh_sach_files", payload[0])

    def test_stage_payload_uppercases_codes(self):
        step = _make_step(self.env, "Sơ chế", "so_che_low")
        site = self.env["crall.production.site"].create(
            {"name": "Cơ sở thường", "code": "cs_low"}
        )
        user = self.env["res.users"].create(
            {"name": "NV Thường", "login": "nv_low", "employee_code": "nv001"}
        )
        dish = self._dish("mon-thuong-001")
        self._line(
            dish, step, sequence=1,
            employee_ids=[(6, 0, [user.id])],
            site_id=site.id,
        )
        payload = dish._supplier_dish_stage_payload()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["ma_khau"], "SO_CHE_LOW")
        self.assertEqual(payload[0]["ma_co_so"], "CS_LOW")
        self.assertEqual(
            payload[0]["danh_sach_nguoi_thuc_hien"], ["NV001"]
        )

    def test_stage_payload_includes_note_and_address(self):
        step = _make_step(self.env, "Sơ chế", "SO_CHE_NOTE")
        dish = self._dish("MON-KHAU-NOTE")
        self._line(
            dish, step, sequence=1,
            info="Rửa sạch, để ráo",
            address="45 Đường Tây Sơn, Hà Nội",
        )
        payload = dish._supplier_dish_stage_payload()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["ghi_chu"], "Rửa sạch, để ráo")
        self.assertEqual(payload[0]["dia_chi"], "45 Đường Tây Sơn, Hà Nội")

    def test_stage_payload_empty_and_stored_fallback(self):
        dish = self._dish("MON-KHAU-003")
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

    def test_form_has_step2_two_columns(self):
        view = self.env.ref("set_top_menu.view_menu_item_form")
        arch = view.arch_db
        self.assertIn("Bước 1", arch)
        self.assertIn("Bước 2: Quy trình chế biến", arch)
        self.assertIn("dish_image_ids", arch)
        self.assertIn("dish_document_ids", arch)
        self.assertIn("stage_line_ids", arch)
        self.assertNotIn("stage_display_ids", arch)
        root = ET.fromstring("<odoo>%s</odoo>" % arch)
        # Bước 2 chỉ hiện khi đã chọn quy trình ở Bước 1: Odoo 17 đánh giá
        # invisible như biểu thức Python nên phải dùng "not process_id",
        # không dùng chuỗi domain (list literal luôn truthy).
        separator = next(
            node
            for node in root.iter("separator")
            if node.get("string") == "Bước 2: Quy trình chế biến"
        )
        self.assertEqual(separator.get("invisible"), "not process_id")
        stage_field = next(
            node
            for node in root.iter("field")
            if node.get("name") == "stage_line_ids"
        )
        self.assertEqual(stage_field.get("invisible"), "not process_id")
        # Bước 2 hiển thị 2 cột qua widget dish_stage_list: cột trái là
        # danh sách khâu, cột phải là form nhập của khâu đang chọn.
        self.assertEqual(stage_field.get("widget"), "dish_stage_list")
        # Subview form khai báo các ô nhập liệu của từng khâu (nạp
        # tên/mã khâu qua field ẩn).
        stage_form = next(node for node in stage_field.iter("form"))
        subview_fields = {
            node.get("name"): node for node in stage_form.iter("field")
        }
        self.assertEqual(
            set(subview_fields),
            {
                "step_id", "step_code", "step_name", "sequence",
                "employee_ids", "site_id", "info", "address", "file_ids",
            },
        )
        for hidden in ("step_id", "step_code", "step_name", "sequence"):
            self.assertEqual(subview_fields[hidden].get("invisible"), "1")
        # Subview tree buộc viewMode="list" để model nạp đúng spec dữ liệu
        # (kể cả tên hiển thị của nhân viên/cơ sở) ở cả chế độ xem lẫn sửa.
        # Widget vẽ giao diện 2 cột, tree này không hiển thị.
        stage_tree = next(node for node in stage_field.iter("tree"))
        self.assertEqual(
            {node.get("name") for node in stage_tree.iter("field")},
            set(subview_fields),
        )

    def test_step2_two_column_widget_structure(self):
        """Widget Bước 2: cột trái lặp danh sách khâu và bấm chọn được,
        cột phải là form nhập của khâu đang chọn.
        """
        template_path = os.path.join(
            get_module_path("set_top_menu"),
            "static", "src", "xml", "dish_stage_list.xml",
        )
        with open(template_path, encoding="utf-8") as handle:
            source = handle.read()
        root = ET.fromstring(source)
        loops = [
            node.get("t-foreach")
            for node in root.iter()
            if node.get("t-foreach")
        ]
        self.assertIn("stages", loops)
        template_text = ET.tostring(root, encoding="unicode")
        self.assertIn("selectStage", template_text)
        self.assertIn("DishStageForm", template_text)
        # Cột phải hiện dòng nội dung khâu đang chọn kèm tên khâu.
        self.assertIn("Đây là nội dung của khâu sản xuất", source)
        # Ô nhập trong cột phải phải bind tên field dạng chuỗi JS,
        # nếu không Field vỡ ở record.fields[name] (lỗi OwlError cũ).
        fields = list(root.iter("Field"))
        self.assertTrue(fields)
        for node in fields:
            name = node.get("name")
            self.assertTrue(
                name.startswith("'") and name.endswith("'"),
                "Unquoted Field name binding: %s" % name,
            )
        # Mỗi khâu nằm trong 1 box cách nhau 15px, box đang chọn nổi bật.
        style_path = os.path.join(
            get_module_path("set_top_menu"),
            "static", "src", "scss", "dish_stage_list.scss",
        )
        with open(style_path, encoding="utf-8") as handle:
            style = handle.read()
        self.assertIn("margin-bottom: 15px", style)
        self.assertIn(".o_dish_stage_active", style)
        # Selector gốc của SCSS phải khớp class gốc của template,
        # nếu không style không bao giờ áp vào màn hình.
        list_template = next(
            node
            for node in root.iter("t")
            if node.get("t-name") == "set_top_menu.DishStageList"
        )
        root_class = list_template.find("div").get("class").split()[0]
        self.assertIn(".%s" % root_class, style)

    def test_stage_list_widget_logs_process_and_stages(self):
        """Widget in console thông tin quy trình + danh sách khâu khi chọn
        quy trình ở Bước 1.
        """
        widget_path = os.path.join(
            get_module_path("set_top_menu"),
            "static", "src", "js", "dish_stage_list.js",
        )
        with open(widget_path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("console.log", source)

    def test_food_form_process_field_uses_expression_invisible(self):
        view = self.env.ref("set_top_menu.view_product_template_food_form")
        arch = view.arch_db
        self.assertNotIn("[('crall_food_source', '=', 'standard')]", arch)
        process_fields = [
            node
            for node in ET.fromstring(
                "<odoo>%s</odoo>" % arch
            ).iter("field")
            if node.get("name") == "process_ids"
        ]
        self.assertTrue(process_fields)
        for node in process_fields:
            self.assertEqual(
                node.get("invisible"), "crall_food_source == 'standard'"
            )


class TestDishPushDirect(TransactionCase):
    def _push(self, dish, response):
        client_path = (
            "odoo.addons.set_top_menu.models.menu_item.HnckClient"
        )
        with patch(client_path) as mock_client:
            mock_client.return_value.push_supplier_dishes.return_value = (
                response
            )
            action = dish.action_push_supplier_dishes()
        return action, mock_client

    def test_push_sends_and_notifies_success(self):
        dish = self.env["set_top_menu.menu.item"].create(
            dict(_dish_vals(self.env), item_code="MON-PUSH-001")
        )
        action, mock_client = self._push(
            dish, {"success": True, "message": "Đã nhận 1 món ăn."}
        )
        body = (
            mock_client.return_value.push_supplier_dishes.call_args[0][0]
        )
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["ma_mon_an"], "MON-PUSH-001")
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
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "success")
        self.assertFalse(action["params"]["sticky"])
        self.assertIn("Đã nhận 1 món ăn.", action["params"]["message"])

    def test_push_api_failure_notifies_danger(self):
        dish = self.env["set_top_menu.menu.item"].create(
            dict(_dish_vals(self.env), item_code="MON-PUSH-002")
        )
        action, _mock_client = self._push(
            dish, {"success": False, "message": "Mã món đã tồn tại."}
        )
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "danger")
        self.assertTrue(action["params"]["sticky"])
        self.assertIn("Mã món đã tồn tại.", action["params"]["message"])

    def test_push_empty_selection_raises(self):
        with self.assertRaises(UserError):
            self.env["set_top_menu.menu.item"].action_push_supplier_dishes()


class TestDishProcessLocked(TransactionCase):
    def _make_process(self, code):
        return self.env["set_top_menu.production.process"].create(
            {"name": "QT %s" % code, "code": code, "product_type": "thuc_an"}
        )

    def test_change_process_on_edit_raises(self):
        proc_a = self._make_process("QT-LOCK-A")
        proc_b = self._make_process("QT-LOCK-B")
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MON-LOCK-001",
                process_id=proc_a.id,
            )
        )
        with self.assertRaises(UserError):
            dish.write({"process_id": proc_b.id})
        with self.assertRaises(UserError):
            dish.write({"process_id": False})

    def test_keep_process_and_edit_other_fields_ok(self):
        proc_a = self._make_process("QT-LOCK-C")
        dish = self.env["set_top_menu.menu.item"].create(
            dict(
                _dish_vals(self.env),
                item_code="MON-LOCK-002",
                process_id=proc_a.id,
            )
        )
        dish.write({"process_id": proc_a.id, "name": "Tên mới"})
        self.assertEqual(dish.name, "Tên mới")
        self.assertEqual(dish.process_id.id, proc_a.id)

    def test_process_readonly_on_edit_view(self):
        view = self.env.ref("set_top_menu.view_menu_item_form")
        seg = view.arch_db.split('name="process_id"')[1].split(">")[0]
        self.assertIn("readonly", seg)
        self.assertIn("id", seg)


class TestMenuItemRequiredFields(TransactionCase):
    def _form_arch(self):
        view = self.env.ref("set_top_menu.view_menu_item_form")
        return ET.fromstring(view.arch_db)

    def test_step1_required_fields_in_form_arch(self):
        arch = self._form_arch()
        by_name = {}
        for node in arch.iter("field"):
            by_name.setdefault(node.get("name"), node)
        for fname in ("process_id", "age_group_id"):
            self.assertIn(fname, by_name)
            self.assertEqual(by_name[fname].get("required"), "1")

    def test_step2_required_fields_in_stage_subview(self):
        arch = self._form_arch()
        stage = [
            node for node in arch.iter("field")
            if node.get("name") == "stage_line_ids"
        ]
        self.assertTrue(stage)
        subform = stage[0].find("form")
        self.assertIsNotNone(subform)
        by_name = {
            node.get("name"): node for node in subform.iter("field")
        }
        for fname in ("employee_ids", "info"):
            self.assertIn(fname, by_name)
            self.assertEqual(by_name[fname].get("required"), "1")
        for fname in ("site_id", "address", "file_ids"):
            self.assertIn(fname, by_name)
            self.assertIsNone(by_name[fname].get("required"))

    def test_required_flags_on_models(self):
        item_fields = self.env["set_top_menu.menu.item"]._fields
        self.assertTrue(item_fields["name"].required)
        self.assertTrue(item_fields["item_code"].required)
        self.assertTrue(item_fields["serving_uom_id"].required)
        stage_fields = self.env["set_top_menu.menu.item.stage"]._fields
        self.assertTrue(stage_fields["employee_ids"].required)
        self.assertTrue(stage_fields["info"].required)
        self.assertFalse(stage_fields["site_id"].required)

    def test_create_without_process_allowed_for_supplier_sync(self):
        dish = self.env["set_top_menu.menu.item"].create(
            _dish_vals(self.env)
        )
        self.assertFalse(dish.process_id)
        self.assertFalse(dish.age_group_id)

    def test_onchange_process_builds_lines_missing_required_inputs(self):
        dish = self.env["set_top_menu.menu.item"].new(_dish_vals(self.env))
        process = _make_process(self.env, code="QT-REQ-001")
        dish.process_id = process
        dish._onchange_process_id()
        self.assertEqual(len(dish.stage_line_ids), 3)
        for line in dish.stage_line_ids:
            self.assertTrue(line.step_id)
            self.assertFalse(line.employee_ids)
            self.assertFalse(line.info)

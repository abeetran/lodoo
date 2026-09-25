import logging
import urllib.parse

import requests

from odoo import _, api, Command, fields, models
from odoo.exceptions import UserError

from odoo.addons.crall_material.models.hnck_client import HnckClient


_logger = logging.getLogger(__name__)

DEFAULT_SUPPLIER_STEP_API_URL = (
    "https://ncc-api.hanoicheck.com.vn/supplier/steps/paginate"
    "?page=1&per_page=15"
)
DEFAULT_SUPPLIER_PROCESS_API_URL = (
    "https://ncc-api.hanoicheck.com.vn/supplier/processes/paginate"
    "?page=1&per_page=15"
)
SUPPLIER_PRODUCT_TYPE_MAP = {
    "food": "thuc_pham",
    "thuc_pham": "thuc_pham",
    "dish": "thuc_an",
    "thuc_an": "thuc_an",
}
# Chiều đẩy lên NCC: thực phẩm (thuc_pham) -> "food",
# món ăn (thuc_an) -> "dish".
PRODUCT_TYPE_TO_SUPPLIER_MAP = {
    "thuc_pham": "food",
    "thuc_an": "dish",
}


class ProductionStep(models.Model):
    _name = "set_top_menu.production.step"
    _description = "Khâu sản xuất"
    _order = "name"

    name = fields.Char(string="Tên khâu sản xuất", required=True, index=True)
    code = fields.Char(
        string="Mã khâu sản xuất", required=True, copy=False, index=True
    )
    note = fields.Text(string="Ghi chú")
    active = fields.Boolean(string="Đang hoạt động", default=True)
    supplier_step_id = fields.Char(
        string="Mã khâu NCC", index=True, copy=False,
        help="id nhận từ API nhà cung cấp.",
    )
    employee_ids = fields.Many2many(
        "res.users",
        string="Nhân viên thực hiện",
        help="Danh sách nhân viên thực hiện khâu sản xuất (lấy từ danh sách người dùng).",
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "Mã khâu sản xuất không được trùng."),
    ]

    def action_push_supplier_steps(self):
        """Nút Đồng bộ: chỉ hiện khi tick chọn khâu trên danh sách.

        Gửi các khâu đang chọn lên API ``supplier/steps/merge`` (POST,
        ký X-Signature; token hết hạn thì tự lấy mới).
        """
        if not self:
            raise UserError(_("Vui lòng chọn ít nhất một khâu sản xuất để đồng bộ."))
        payloads = [
            {"ma_khau": step.code or "", "ten_khau": step.name or ""}
            for step in self
        ]
        result = HnckClient(self.env).push_supplier_steps(payloads)
        message = _("Đã gửi %s khâu sản xuất lên API nhà cung cấp.") % len(payloads)
        if isinstance(result, dict) and result.get("message"):
            message = "%s %s" % (message, result["message"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đồng bộ khâu sản xuất"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_create_popup(self):
        """Nút Thêm mới: mở form tạo khâu trong dialog (popup).

        Popup tạo mới ẩn trường nhân viên thực hiện; trường này chỉ
        nhập ở màn hình cập nhật (form đầy đủ).
        """
        form_view = self.env.ref("set_top_menu.view_production_step_form_create")
        return {
            "type": "ir.actions.act_window",
            "name": "Thêm khâu sản xuất",
            "res_model": "set_top_menu.production.step",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "target": "new",
        }

    @api.model
    def sync_supplier_steps(self, url=None, token=None, referer=None,
                            page=1, per_page=15):
        """Lấy 1 trang khâu SX từ API nhà cung cấp về QL khâu SX.

        ``token``/``page`` lấy từ form Data Sync; bản ghi đã tồn tại theo
        ``supplier_step_id`` (rồi tới ``code``) thì cập nhật, chưa có thì tạo.
        """
        parameters = self.env["ir.config_parameter"].sudo()
        url = url or parameters.get_param(
            "crall_material.supplier_step_api_url",
            DEFAULT_SUPPLIER_STEP_API_URL,
        )
        token = token or parameters.get_param("crall_material.supplier_api_token")
        referer = referer or parameters.get_param(
            "crall_material.supplier_api_referer",
            "https://ncc.hanoicheck.com.vn",
        )
        if not token:
            raise UserError(_("Chưa cấu hình token API của nhà cung cấp."))
        if not token.lower().startswith("bearer "):
            token = "Bearer %s" % token

        request_url = self._supplier_steps_page_url(url, page, per_page)
        try:
            response = requests.get(
                request_url,
                headers={
                    "Authorization": token,
                    "Referer": referer,
                    "Accept": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as error:
            _logger.exception("Could not fetch supplier steps")
            raise UserError(
                _("Không thể lấy dữ liệu khâu sản xuất: %s") % error
            ) from error
        except ValueError as error:
            raise UserError(_("API trả về dữ liệu JSON không hợp lệ.")) from error

        steps = self._supplier_step_list(payload)
        if not steps:
            raise UserError(_("Không có dữ liệu ở trang %s.") % page)

        created = updated = skipped = 0
        for step in steps:
            if not isinstance(step, dict):
                skipped += 1
                continue
            supplier_id = step.get("id")
            name = step.get("name")
            if supplier_id in (None, "", False) or not name:
                _logger.warning("Skipping supplier step without id or name: %s", step)
                skipped += 1
                continue
            supplier_id = str(supplier_id)
            code = step.get("code") or False
            values = {
                "name": str(name),
                "code": code or "NCC-%s" % supplier_id,
                "note": step.get("note") or False,
                "supplier_step_id": supplier_id,
            }
            existing = self.search([("supplier_step_id", "=", supplier_id)], limit=1)
            if not existing and code:
                existing = self.search([("code", "=", str(code))], limit=1)
            if existing:
                existing.write(values)
                updated += 1
                continue
            self.create(values)
            created += 1

        _logger.info(
            "Supplier steps synchronized: page %s (per_page %s), "
            "%s created, %s updated, %s skipped",
            page, per_page, created, updated, skipped,
        )
        return {"created": created, "updated": updated, "skipped": skipped}

    @staticmethod
    def _supplier_steps_page_url(url, page, per_page):
        parts = urllib.parse.urlsplit((url or "").strip())
        query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(
                parts.query, keep_blank_values=True
            )
            if key not in ("page", "per_page")
        ]
        query.append(("page", str(page)))
        query.append(("per_page", str(per_page)))
        return urllib.parse.urlunsplit(
            parts._replace(query=urllib.parse.urlencode(query))
        )

    @staticmethod
    def _supplier_step_list(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("data", "items", "results", "steps"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = ProductionStep._supplier_step_list(value)
                if nested:
                    return nested
        return []


class ProductionProcess(models.Model):
    _name = "set_top_menu.production.process"
    _description = "Quy trình sản xuất"
    _order = "name"

    name = fields.Char(string="Tên quy trình", required=True, index=True)
    code = fields.Char(
        string="Mã quy trình", required=True, copy=False, index=True
    )
    product_type = fields.Selection(
        [("thuc_pham", "Thực phẩm"), ("thuc_an", "Thức ăn")],
        string="Loại sản phẩm",
        required=True,
        default="thuc_pham",
    )
    line_ids = fields.One2many(
        "set_top_menu.production.process.line",
        "process_id",
        string="Danh sách khâu",
    )
    step_count = fields.Integer(
        string="Số khâu",
        compute="_compute_step_count",
        store=True,
        readonly=True,
    )
    note = fields.Text(string="Ghi chú")
    active = fields.Boolean(string="Đang hoạt động", default=True)
    supplier_process_id = fields.Char(
        string="Mã quy trình NCC", index=True, copy=False,
        help="id nhận từ API nhà cung cấp.",
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "Mã quy trình không được trùng."),
    ]

    @api.depends("line_ids")
    def _compute_step_count(self):
        for process in self:
            process.step_count = len(process.line_ids)

    def action_push_supplier_processes(self):
        """Nút Đồng bộ: chỉ hiện khi tick chọn quy trình trên danh sách.

        Gửi các quy trình đang chọn lên API ``supplier/processes/merge``
        (POST, ký X-Signature; token hết hạn thì tự lấy mới).
        """
        if not self:
            raise UserError(_("Vui lòng chọn ít nhất một quy trình sản xuất để đồng bộ."))
        payloads = [process._supplier_process_push_payload() for process in self]
        result = HnckClient(self.env).push_supplier_processes(payloads)
        message = _("Đã gửi %s quy trình sản xuất lên API nhà cung cấp.") % len(payloads)
        if isinstance(result, dict) and result.get("message"):
            message = "%s %s" % (message, result["message"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đồng bộ quy trình sản xuất"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def _supplier_process_push_payload(self):
        """Serialize one process into the supplier merge body format."""
        self.ensure_one()
        return {
            "ma_quy_trinh": self.code or "",
            "ten_quy_trinh": self.name or "",
            "loai_san_pham": PRODUCT_TYPE_TO_SUPPLIER_MAP.get(
                self.product_type or "", self.product_type or ""
            ),
            "danh_sach_khau": [
                {
                    "ma_khau": line.step_id.code or "",
                    "thu_tu": line.sequence or 0,
                }
                for line in self.line_ids.sorted("sequence")
            ],
        }

    @api.model
    def sync_supplier_processes(self, url=None, token=None, referer=None,
                                page=1, per_page=15):
        """Lấy quy trình SX từ API nhà cung cấp về QL Quy trình SX.

        ``token``/``page`` lấy từ form Data Sync. Với mỗi quy trình trong
        trang paginate, gọi tiếp API chi tiết để lấy danh sách khâu
        (``steps``) rồi lưu vào quy trình cùng các dòng khâu theo ``order``.
        """
        parameters = self.env["ir.config_parameter"].sudo()
        url = url or parameters.get_param(
            "crall_material.supplier_process_api_url",
            DEFAULT_SUPPLIER_PROCESS_API_URL,
        )
        token = token or parameters.get_param("crall_material.supplier_api_token")
        referer = referer or parameters.get_param(
            "crall_material.supplier_api_referer",
            "https://ncc.hanoicheck.com.vn",
        )
        if not token:
            raise UserError(_("Chưa cấu hình token API của nhà cung cấp."))
        if not token.lower().startswith("bearer "):
            token = "Bearer %s" % token

        headers = {
            "Authorization": token,
            "Referer": referer,
            "Accept": "application/json",
        }
        request_url = self._supplier_paginated_url(url, page, per_page)
        payload = self._supplier_get_json(request_url, headers)
        processes = self._supplier_process_list(payload)
        if not processes:
            raise UserError(_("Không có dữ liệu ở trang %s.") % page)

        created = updated = skipped = 0
        for item in processes:
            if not isinstance(item, dict):
                skipped += 1
                continue
            supplier_id = item.get("id")
            if supplier_id in (None, "", False):
                _logger.warning("Skipping supplier process without id: %s", item)
                skipped += 1
                continue
            supplier_id = str(supplier_id)
            detail = self._unwrap_detail(
                self._supplier_get_json(
                    self._supplier_process_detail_url(url, supplier_id), headers
                )
            )
            if not isinstance(detail, dict):
                _logger.warning(
                    "Skipping supplier process %s: detail API không trả về JSON object.",
                    supplier_id,
                )
                skipped += 1
                continue
            if self._sync_supplier_process_detail(supplier_id, item, detail):
                created += 1
            else:
                updated += 1

        _logger.info(
            "Supplier processes synchronized: page %s (per_page %s), "
            "%s created, %s updated, %s skipped",
            page, per_page, created, updated, skipped,
        )
        return {"created": created, "updated": updated, "skipped": skipped}

    def _sync_supplier_process_detail(self, supplier_id, item, detail):
        """Lưu 1 quy trình + dòng khâu. Trả về True nếu tạo mới."""
        name = detail.get("name") or item.get("name")
        if not name:
            _logger.warning(
                "Skipping supplier process without name: %s", supplier_id
            )
            return False
        code = detail.get("code") or item.get("code") or False
        product_type = SUPPLIER_PRODUCT_TYPE_MAP.get(
            (detail.get("product_type") or item.get("product_type") or "").strip()
        )
        if not product_type:
            _logger.warning(
                "Unknown product_type %r for supplier process %s, dùng mặc định.",
                detail.get("product_type") or item.get("product_type"),
                supplier_id,
            )
            product_type = "thuc_pham"
        status = detail.get("status", item.get("status"))
        values = {
            "name": str(name),
            "code": str(code) if code else "NCC-QT-%s" % supplier_id,
            "product_type": product_type,
            "active": status in (None, "", "active"),
            "supplier_process_id": supplier_id,
        }
        values["line_ids"] = self._supplier_process_line_commands(
            detail.get("steps") or []
        )
        _logger.info(
            "Supplier process %s (%s): %d steps parsed",
            supplier_id,
            values["code"],
            len(values["line_ids"]) - 1 if values["line_ids"] else 0,
        )
        existing = self.search([("supplier_process_id", "=", supplier_id)], limit=1)
        if not existing and code:
            existing = self.search([("code", "=", str(code))], limit=1)
        if existing:
            if not values["line_ids"]:
                values.pop("line_ids")
            existing.write(values)
            return False
        self.create(values)
        return True

    def _supplier_process_line_commands(self, steps):
        """Dựng dòng khâu theo ``order`` từ API chi tiết."""
        step_model = self.env["set_top_menu.production.step"]
        commands = [Command.clear()]
        lines = 0
        for position, entry in enumerate(steps if isinstance(steps, list) else [], 1):
            if not isinstance(entry, dict):
                continue
            supplier_step_id = entry.get("supplier_step_id", entry.get("id"))
            if supplier_step_id in (None, "", False):
                continue
            supplier_step_id = str(supplier_step_id)
            step = step_model.search(
                [("supplier_step_id", "=", supplier_step_id)], limit=1
            )
            if not step:
                step_name = entry.get("name")
                step_code = entry.get("code")
                if not step_name and not step_code:
                    continue
                step = step_model.create(
                    {
                        "name": str(step_name or step_code),
                        "code": str(step_code)
                        if step_code
                        else "NCC-%s" % supplier_step_id,
                        "supplier_step_id": supplier_step_id,
                    }
                )
            try:
                order = int(entry.get("order") or position)
            except (TypeError, ValueError):
                order = position
            commands.append(
                Command.create(
                    {"step_id": step.id, "sequence": order}
                )
            )
            lines += 1
        return commands if lines else []

    def _supplier_get_json(self, request_url, headers):
        try:
            response = requests.get(request_url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as error:
            _logger.exception("Could not fetch supplier processes")
            raise UserError(
                _("Không thể lấy dữ liệu quy trình sản xuất: %s") % error
            ) from error
        except ValueError as error:
            raise UserError(_("API trả về dữ liệu JSON không hợp lệ.")) from error

    @staticmethod
    def _supplier_paginated_url(url, page, per_page):
        parts = urllib.parse.urlsplit((url or "").strip())
        query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(
                parts.query, keep_blank_values=True
            )
            if key not in ("page", "per_page")
        ]
        query.append(("page", str(page)))
        query.append(("per_page", str(per_page)))
        return urllib.parse.urlunsplit(
            parts._replace(query=urllib.parse.urlencode(query))
        )

    @staticmethod
    def _supplier_process_detail_url(url, supplier_id):
        parts = urllib.parse.urlsplit((url or "").strip())
        base = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        return "%s/supplier/processes/%s" % (base.rstrip("/"), supplier_id)

    @staticmethod
    def _unwrap_detail(payload):
        """Bóc lớp bọc ngoài của API chi tiết (nếu có).

        API có thể trả object trần (có ``steps``) hoặc bọc trong
        ``{"data": {...}}`` / ``{"item": ...}`` / ``{"result": ...}``
        hoặc list 1 phần tử. Trả về dict chi tiết hoặc payload gốc.
        """
        if isinstance(payload, dict) and "steps" in payload:
            return payload
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return ProductionProcess._unwrap_detail(payload[0])
        if isinstance(payload, dict):
            for key in ("data", "item", "result", "process"):
                value = payload.get(key)
                if isinstance(value, (dict, list)):
                    unwrapped = ProductionProcess._unwrap_detail(value)
                    if isinstance(unwrapped, dict) and (
                        "steps" in unwrapped or "id" in unwrapped
                    ):
                        return unwrapped
        return payload

    @staticmethod
    def _supplier_process_list(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("data", "items", "results", "processes"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = ProductionProcess._supplier_process_list(value)
                if nested:
                    return nested
        return []


class ProductionProcessLine(models.Model):
    _name = "set_top_menu.production.process.line"
    _description = "Khâu của quy trình sản xuất"
    _order = "sequence, id"

    process_id = fields.Many2one(
        "set_top_menu.production.process",
        string="Quy trình",
        required=True,
        ondelete="cascade",
        index=True,
    )
    step_id = fields.Many2one(
        "set_top_menu.production.step",
        string="Khâu SX",
        required=True,
        ondelete="restrict",
    )
    sequence = fields.Integer(string="Thứ tự", default=10)
    number = fields.Integer(
        string="STT",
        compute="_compute_number",
        readonly=True,
    )

    @api.depends("process_id.line_ids.sequence", "process_id.line_ids.step_id")
    def _compute_number(self):
        for line in self:
            if not line.process_id:
                line.number = 0
                continue
            # Chỉ sort theo sequence (không kèm id): id của dòng chưa lưu
            # là NewId, không so sánh < được nên sort sẽ crash (xem traceback).
            # sorted của Python ổn định nên các dòng cùng sequence giữ đúng
            # thứ tự nhập.
            ordered = line.process_id.line_ids.sorted(
                key=lambda item: item.sequence
            )
            line.number = next(
                (
                    index
                    for index, item in enumerate(ordered, start=1)
                    if item.id == line.id
                ),
                0,
            )

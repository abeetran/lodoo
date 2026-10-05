from urllib.parse import urlencode, urlsplit

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.crall_material.models.hnck_client import (
    ORDERS_FETCH_PATH,
    HnckClient,
)


class OrderFetchWizard(models.TransientModel):
    _name = "set_top_menu.order.fetch.wizard"
    _description = "Lấy đơn hàng từ HNCK"

    order_code = fields.Char(string="Mã đơn hàng")
    school_id = fields.Many2one(
        "res.partner",
        string="Trường học",
        domain=[("customer_rank", ">", 0)],
    )
    page = fields.Integer(string="Trang")
    status = fields.Selection(
        [
            ("ALL", "Tất cả"),
            ("CHO_XAC_NHAN", "Chờ xác nhận"),
            ("TU_CHOI", "Từ chối"),
            ("DANG_CHUAN_BI", "Đang chuẩn bị"),
            ("DANG_GIAO", "Đang giao"),
            ("DA_GIAO", "Đã giao"),
            ("GIAO_HANG_THANH_CONG", "Giao hàng thành công"),
            ("TRA_HANG", "Trả hàng"),
            ("HUY", "Hủy"),
        ],
        string="Trạng thái",
        required=True,
        default="ALL",
    )
    order_date_from = fields.Date(string="Từ ngày đặt")
    order_date_to = fields.Date(string="Đến ngày đặt")
    state = fields.Selection(
        [("draft", "Chờ xác nhận"), ("done", "Đã lấy")],
        string="Trạng thái",
        default="draft",
        required=True,
    )
    result_text = fields.Text(string="Kết quả", readonly=True)
    x_nonce = fields.Char(
        string="X-Nonce",
        readonly=True,
        default=lambda records: HnckClient.new_nonce(),
    )
    x_timestamp = fields.Char(
        string="X-Timestamp",
        readonly=True,
        default=lambda records: HnckClient(records.env).timestamp(),
    )
    preview_text = fields.Text(
        string="Thông tin request",
        readonly=True,
        compute="_compute_preview",
    )

    def _fetch_args(self):
        """Map trường popup thành tham số gọi API (trống thì bỏ)."""
        self.ensure_one()
        return {
            "page": self.page,
            "status": self.status if self.status != "ALL" else False,
            "date_from": self.order_date_from,
            "date_to": self.order_date_to,
            "order_code": self.order_code,
            "school_id": self.school_id.school_code,
        }

    @staticmethod
    def _mask_token(token):
        if not token:
            return ""
        if len(token) <= 10:
            return token[:2] + "..." + token[-2:]
        return token[:6] + "..." + token[-4:]

    @api.depends(
        "order_code",
        "school_id",
        "status",
        "order_date_from",
        "order_date_to",
        "page",
        "x_nonce",
        "x_timestamp",
    )
    def _compute_preview(self):
        """In method, URL và header sẽ gửi để kiểm tra trước khi lấy."""
        for wizard in self:
            params = self.env["sale.order"]._order_fetch_params(
                **wizard._fetch_args()
            )
            client = HnckClient(wizard.env)
            try:
                request_url = client.base_url() + ORDERS_FETCH_PATH
            except UserError:
                request_url = _("(chưa cấu hình HNCK API URL)")
            query = urlencode(
                {key: value for key, value in params.items() if value}
            )
            if query and not request_url.startswith("("):
                request_url = "%s?%s" % (request_url, query)
            token, token_valid = client.peek_cached_token()
            if token and token_valid:
                token_type = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_param("crall_material.hnck_token_type")
                    or "Bearer"
                )
                if token.lower().startswith("bearer "):
                    auth_display = self._mask_token(token)
                else:
                    auth_display = "%s %s" % (
                        token_type,
                        self._mask_token(token),
                    )
            else:
                auth_display = _("(sẽ lấy token mới khi xác nhận)")
            try:
                signature = client.signature(
                    "GET",
                    urlsplit(request_url).path,
                    wizard.x_timestamp,
                    wizard.x_nonce,
                    b"",
                )
            except UserError:
                signature = _("(chưa cấu hình HMAC secret)")
            wizard.preview_text = "\n".join(
                [
                    "Method: GET",
                    "URL: %s" % request_url,
                    "Headers:",
                    "  Authorization: %s" % auth_display,
                    "  Accept: application/json",
                    "  X-Timestamp: %s" % wizard.x_timestamp,
                    "  X-Nonce: %s" % wizard.x_nonce,
                    "  X-Signature: %s" % signature,
                ]
            )

    def action_confirm_fetch(self):
        """Nút Xác nhận: gọi API lấy đơn hàng rồi hiện kết quả."""
        self.ensure_one()
        counts = self.env["sale.order"].fetch_supplier_orders(
            **self._fetch_args(),
            x_nonce=self.x_nonce,
            x_timestamp=self.x_timestamp,
        )
        result_text = "\n".join(
            [
                _("Đã lấy %(fetched)s đơn hàng (tổng %(total)s).") % counts,
                _("Tạo mới: %(created)s") % counts,
                _("Cập nhật: %(updated)s") % counts,
                _("Bỏ qua (thiếu mã): %(skipped_no_code)s") % counts,
                _("Bỏ qua (bếp đang làm): %(skipped_locked)s") % counts,
                _(
                    "Dòng sản phẩm: %(lines_ok)s hợp lệ, "
                    "%(lines_skipped)s bỏ qua."
                )
                % counts,
                _("Khách hàng mới: %(partners_created)s.") % counts,
            ]
        )
        self.write({"state": "done", "result_text": result_text})
        form_view = self.env.ref("set_top_menu.view_order_fetch_wizard_form")
        return {
            "type": "ir.actions.act_window",
            "name": _("Kết quả lấy đơn hàng"),
            "res_model": "set_top_menu.order.fetch.wizard",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "res_id": self.id,
            "target": "new",
        }

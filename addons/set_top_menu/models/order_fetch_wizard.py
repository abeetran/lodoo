from odoo import _, fields, models


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

    def action_confirm_fetch(self):
        """Nút Xác nhận: gọi API lấy đơn hàng rồi hiện kết quả."""
        self.ensure_one()
        counts = self.env["sale.order"].fetch_supplier_orders(
            **self._fetch_args()
        )
        result_text = "\n".join(
            [
                _("Đã lấy %(fetched)s đơn hàng (tổng %(total)s).") % counts,
                _("Tạo mới: %(created)s") % counts,
                _("Cập nhật: %(updated)s") % counts,
                _("Bỏ qua (thiếu mã): %(skipped_no_code)s") % counts,
                _("Bỏ qua (đơn nhập tay): %(skipped_manual)s") % counts,
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

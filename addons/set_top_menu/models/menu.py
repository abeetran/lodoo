from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.crall_material.models.hnck_client import HnckClient

WEEKDAY_NUMBERS = {
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
    "sun": 7,
}


class Menu(models.Model):
    _name = "set_top_menu.menu"
    _description = "Thực đơn"
    _order = "name"

    name = fields.Char(string="Tên thực đơn", required=True, index=True)
    code = fields.Char(
        string="Mã thực đơn", required=True, copy=False, index=True
    )
    age_group_id = fields.Many2one(
        "set_top_menu.age.group",
        string="Nhóm tuổi",
        required=True,
        ondelete="restrict",
        help="Đối tượng áp dụng thực đơn (lấy từ danh sách nhóm tuổi).",
    )
    weekday = fields.Selection(
        [
            ("mon", "Thứ 2"),
            ("tue", "Thứ 3"),
            ("wed", "Thứ 4"),
            ("thu", "Thứ 5"),
            ("fri", "Thứ 6"),
            ("sat", "Thứ 7"),
            ("sun", "Chủ nhật"),
        ],
        string="Thứ áp dụng",
        required=True,
    )
    status = fields.Selection(
        [("applying", "Đang áp dụng"), ("stopped", "Ngừng áp dụng")],
        string="Trạng thái",
        required=True,
        default="applying",
        index=True,
    )
    school_ids = fields.Many2many(
        "res.partner",
        relation="set_top_menu_menu_school_rel",
        column1="menu_id",
        column2="partner_id",
        string="Trường áp dụng",
        domain=[("school_code", "!=", False)],
        help="Phạm vi áp dụng thực đơn (chọn nhiều trường).",
    )
    note = fields.Text(string="Ghi chú")
    active = fields.Boolean(string="Đang hoạt động", default=True)
    audience_schedule_display = fields.Char(
        string="Đối tượng và lịch áp dụng",
        compute="_compute_audience_schedule_display",
        help="Cột hiển thị gộp nhóm tuổi và thứ áp dụng trên danh sách.",
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "Mã thực đơn không được trùng."),
    ]

    def action_push_supplier_menus(self):
        """Nút Đồng bộ: chỉ hiện khi tick chọn thực đơn trên danh sách.

        Gửi các thực đơn đang chọn lên API ``supplier/menus/merge`` (POST,
        ký X-Signature; token hết hạn thì tự lấy mới).
        """
        if not self:
            raise UserError(_("Vui lòng chọn ít nhất một thực đơn để đồng bộ."))
        payloads = [menu._supplier_menu_push_payload() for menu in self]
        result = HnckClient(self.env).push_supplier_menus(payloads)
        message = _("Đã gửi %s thực đơn lên API nhà cung cấp.") % len(payloads)
        if isinstance(result, dict) and result.get("message"):
            message = "%s %s" % (message, result["message"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đồng bộ thực đơn"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def _supplier_menu_push_payload(self):
        """Serialize one menu into the supplier merge body format."""
        self.ensure_one()
        age_group = self.age_group_id
        schools = self.school_ids.filtered("school_code")
        return {
            "ma_thuc_don": (self.code or "").upper(),
            "ten_thuc_don": self.name or "",
            "nhom_tuoi_id": self._supplier_int(
                age_group.supplier_age_id if age_group else False
            ),
            "thu_ap_dung": WEEKDAY_NUMBERS.get(self.weekday, 0),
            "trang_thai": self.status == "applying",
            # Chưa có dữ liệu dòng món: giữ rỗng, bổ sung khi có model dòng.
            "danh_sach_mon": [],
            "danh_sach_truong": sorted(
                school_id
                for school_id in (
                    self._supplier_int(code)
                    for code in schools.mapped("school_code")
                )
                if school_id
            ),
        }

    @staticmethod
    def _supplier_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @api.depends("age_group_id.name", "weekday")
    def _compute_audience_schedule_display(self):
        weekdays = dict(
            self._fields["weekday"].selection or []
        )
        for menu in self:
            parts = [
                menu.age_group_id.name or "",
                weekdays.get(menu.weekday) or "",
            ]
            menu.audience_schedule_display = " - ".join(
                [part for part in parts if part]
            )

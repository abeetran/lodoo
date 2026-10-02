from odoo import api, fields, models


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

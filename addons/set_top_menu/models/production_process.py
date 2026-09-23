from odoo import api, fields, models


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

    _sql_constraints = [
        ("code_unique", "unique(code)", "Mã khâu sản xuất không được trùng."),
    ]

    def action_open_create_popup(self):
        """Nút Thêm mới: mở form tạo khâu trong dialog (popup)."""
        form_view = self.env.ref("set_top_menu.view_production_step_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Thêm khâu sản xuất",
            "res_model": "set_top_menu.production.step",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "target": "new",
        }


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

    _sql_constraints = [
        ("code_unique", "unique(code)", "Mã quy trình không được trùng."),
    ]

    @api.depends("line_ids")
    def _compute_step_count(self):
        for process in self:
            process.step_count = len(process.line_ids)


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

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Warehouse(models.Model):
    _name = "set_top_menu.warehouse"
    _description = "Kho"
    _order = "name"

    name = fields.Char(string="Tên kho", required=True, index=True)
    code = fields.Char(
        string="Mã kho", required=True, copy=False, index=True
    )
    address = fields.Char(string="Địa chỉ", required=True)
    area = fields.Float(
        string="Diện tích (m²)",
        digits=(10, 2),
        help="Diện tích kho tính bằng mét vuông (m²).",
    )
    active = fields.Boolean(string="Đang hoạt động", default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "Mã kho không được trùng."),
    ]

    @api.constrains("area")
    def _check_area(self):
        for warehouse in self:
            if warehouse.area and warehouse.area < 0:
                raise ValidationError("Diện tích kho không được âm.")

    def action_open_create_popup(self):
        """Nút Thêm mới: mở form tạo kho trong dialog (popup)."""
        form_view = self.env.ref("set_top_menu.view_warehouse_form_create")
        return {
            "type": "ir.actions.act_window",
            "name": "Thêm kho mới",
            "res_model": "set_top_menu.warehouse",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "target": "new",
        }

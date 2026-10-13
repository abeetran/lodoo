from odoo import api, fields, models


class DeliveryStaff(models.Model):
    _name = "set_top_menu.delivery.staff"
    _description = "Nhân viên giao hàng"
    _order = "name"

    name = fields.Char(string="Tên nhân viên", required=True, index=True)
    code = fields.Char(string="Mã nhân viên", copy=False, index=True)
    phone = fields.Char(string="Điện thoại")
    order_ids = fields.One2many(
        "sale.order", "transporter_id", string="Đơn hàng"
    )
    order_count = fields.Integer(
        string="Số đơn giao", compute="_compute_order_count"
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "Mã nhân viên đã tồn tại."),
    ]

    @api.depends("order_ids")
    def _compute_order_count(self):
        for staff in self:
            staff.order_count = len(staff.order_ids)

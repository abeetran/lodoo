from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    employee_code = fields.Char(
        string="Mã nhân viên",
        copy=False,
        index=True,
        help="Mã nhân viên của người dùng.",
    )

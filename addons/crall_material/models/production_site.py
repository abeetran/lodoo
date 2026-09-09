from odoo import fields, models


class CrallProductionSite(models.Model):
    _name = "crall.production.site"
    _description = "Crall Production Site"
    _order = "name"

    name = fields.Char(string="Tên cơ sở", required=True)
    code = fields.Char(string="Mã cơ sở", copy=False)
    address = fields.Char(string="Địa chỉ")
    phone = fields.Char(string="Điện thoại")
    tax_number = fields.Char(string="Mã số thuế")
    supplier_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp",
        domain=[("crall_sub_supplier_id", "!=", False)],
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")

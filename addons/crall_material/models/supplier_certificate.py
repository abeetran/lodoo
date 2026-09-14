from odoo import fields, models


class CrallSupplierCertificate(models.Model):
    _name = "crall.supplier.certificate"
    _description = "Giấy chứng nhận ATTP"
    _order = "ngay_het_han, id"

    partner_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp",
        required=True,
        ondelete="cascade",
    )
    ten_giay_chung_nhan = fields.Char(string="Tên giấy chứng nhận")
    so_giay = fields.Char(string="Số giấy")
    ngay_cap = fields.Date(string="Ngày cấp")
    ngay_het_han = fields.Date(string="Ngày hết hạn")

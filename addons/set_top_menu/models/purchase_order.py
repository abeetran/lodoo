from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # Dropdown ĐVT dòng mua xổ đủ danh sách như khi tạo món (gỡ lọc cùng
    # nhóm của Odoo lõi).
    product_uom = fields.Many2one(domain="[]")

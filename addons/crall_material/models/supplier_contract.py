from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrallSupplierContract(models.Model):
    _name = "crall.supplier.contract"
    _description = "Hợp đồng nhà cung cấp"
    _order = "ngay_het_han, id"

    partner_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp",
        required=True,
        ondelete="cascade",
    )
    so_hd = fields.Char(string="Số hợp đồng")
    ngay_ky = fields.Date(string="Ngày ký")
    ngay_het_han = fields.Date(string="Ngày hết hạn")
    line_ids = fields.One2many(
        "crall.supplier.contract.line",
        "contract_id",
        string="Chi tiết hợp đồng",
        copy=True,
    )
    amount = fields.Float(
        string="Giá trị hợp đồng",
        compute="_compute_amount",
        store=True,
    )
    notes = fields.Text(string="Ghi chú")

    @api.depends("line_ids.subtotal")
    def _compute_amount(self):
        for contract in self:
            contract.amount = sum(contract.line_ids.mapped("subtotal"))


class CrallSupplierContractLine(models.Model):
    _name = "crall.supplier.contract.line"
    _description = "Chi tiết hợp đồng nhà cung cấp"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    contract_id = fields.Many2one(
        "crall.supplier.contract",
        string="Hợp đồng",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm / Nguyên liệu",
        required=True,
        domain="[('purchase_ok', '=', True)]",
    )
    name = fields.Text(string="Mô tả", required=True)
    quantity = fields.Float(string="Số lượng", required=True, default=1.0)
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Đơn vị",
        required=True,
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    product_uom_category_id = fields.Many2one(
        related="product_id.uom_id.category_id",
        depends=["product_id"],
    )
    price_unit = fields.Float(string="Đơn giá", required=True, default=0.0)
    subtotal = fields.Float(
        string="Thành tiền",
        compute="_compute_subtotal",
        store=True,
    )

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.product_uom_id = self.product_id.uom_id
            self.price_unit = self.product_id.standard_price

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Số lượng phải lớn hơn 0.")

    def action_delete_contract_line(self):
        # Kept for compatibility with cached views that may still call it.
        # The Hop dong tab now deletes through the list delete control.
        self.ensure_one()
        if isinstance(self.id, int):
            self.unlink()
        return True

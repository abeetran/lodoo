from odoo import api, fields, models
from odoo.tools.float_utils import float_compare


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    catering_has_remaining = fields.Boolean(
        string="Còn hàng phải nhập",
        compute="_compute_catering_has_remaining",
        store=True,
        help="Còn ít nhất một dòng kho đặt mua nhiều hơn đã nhập, dùng "
        "để cho chọn đơn mua trên phiếu nhập kho.",
    )

    @api.depends(
        "order_line.display_type",
        "order_line.product_id",
        "order_line.product_qty",
        "order_line.qty_received",
    )
    def _compute_catering_has_remaining(self):
        """Còn hàng phải nhập theo cùng luật sinh dòng của phiếu nhập."""
        for order in self:
            remaining = False
            for line in order.order_line.filtered(
                lambda item: not item.display_type
                and item.product_id
                and item.product_id.type in ("product", "consu")
            ):
                rounding = (
                    line.product_uom or line.product_id.uom_id
                ).rounding or 0.01
                if (
                    float_compare(
                        line.product_qty,
                        line.qty_received,
                        precision_rounding=rounding,
                    )
                    > 0
                ):
                    remaining = True
                    break
            order.catering_has_remaining = remaining


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # Dropdown ĐVT dòng mua xổ đủ danh sách như khi tạo món (gỡ lọc cùng
    # nhóm của Odoo lõi).
    product_uom = fields.Many2one(domain="[]")

    # Chụp trigger lần định giá gần nhất: lõi tính lại đơn giá mỗi lần
    # đổi số lượng (chọn lại chiết khấu theo lượng của NCC) khiến giá
    # nhảy loạn. Chỉ tính lại khi đổi sản phẩm, ĐVT hoặc công ty; đổi số
    # lượng giữ nguyên đơn giá đang có.
    # NOTE: @api.depends gộp qua các lớp kế thừa nên không thể gỡ trigger
    # bằng depends mới — phải chặn trong thân hàm qua snapshot này.
    catering_price_product_id = fields.Many2one(
        "product.product", string="Định giá theo SP"
    )
    catering_price_uom_id = fields.Many2one(
        "uom.uom", string="Định giá theo ĐVT"
    )
    catering_price_company_id = fields.Many2one(
        "res.company", string="Định giá theo công ty"
    )

    @api.depends("product_id", "product_uom", "company_id")
    def _compute_price_unit_and_date_planned_and_name(self):
        to_price = self.filtered(
            lambda line: line._catering_price_trigger_changed()
        )
        if to_price:
            super(
                PurchaseOrderLine, to_price
            )._compute_price_unit_and_date_planned_and_name()
            to_price._catering_price_snapshot_triggers()

    def _catering_price_trigger_changed(self):
        self.ensure_one()
        return (
            not self.catering_price_product_id
            or self.product_id != self.catering_price_product_id
            or self.product_uom != self.catering_price_uom_id
            or self.company_id != self.catering_price_company_id
        )

    def _catering_price_snapshot_triggers(self):
        for line in self:
            line.catering_price_product_id = line.product_id
            line.catering_price_uom_id = line.product_uom
            line.catering_price_company_id = line.company_id

    def write(self, vals):
        # Chốt chặn cuối cho giá ổn định: đổi số lượng (không kèm đổi
        # SP/ĐVT/công ty) thì giữ nguyên đơn giá sau khi lõi tính lại.
        # Giá ghi rõ trong vals luôn thắng (giữ lựa chọn tay của user).
        if {"product_id", "product_uom", "company_id"} & set(vals):
            return super().write(vals)
        saved = {
            line.id: (
                vals.get("price_unit", line.price_unit),
                vals.get("discount", line.discount),
            )
            for line in self
        }
        result = super().write(vals)
        for line in self:
            price, discount = saved[line.id]
            if line.price_unit != price or line.discount != discount:
                super(PurchaseOrderLine, line).write(
                    {"price_unit": price, "discount": discount}
                )
        return result

    @api.depends("product_uom", "product_qty", "product_id.uom_id")
    def _compute_product_uom_qty(self):
        """ĐVT mua độc lập: khác nhóm ĐVT hàng thì giữ nguyên số lượng.

        Lõi ép quy đổi sang ĐVT kho và báo lỗi khi khác nhóm; ở đây chỉ
        quy đổi khi cùng nhóm, còn lại lấy số thô như phía đơn bán.
        """
        same = self.filtered(
            lambda line: not line.product_id
            or not line.product_uom
            or line.product_uom.id == line.product_id.uom_id.id
            or line.product_uom.category_id.id
            == line.product_id.uom_id.category_id.id
        )
        rest = self - same
        if same:
            super(PurchaseOrderLine, same)._compute_product_uom_qty()
        for line in rest:
            line.product_uom_qty = line.product_qty

    def _get_gross_price_unit(self):
        """ĐVT mua độc lập: khác nhóm thì bỏ hệ số quy đổi giá vốn."""
        self.ensure_one()
        if (
            self.product_id
            and self.product_uom
            and self.product_uom.id != self.product_id.uom_id.id
            and self.product_uom.category_id.id
            != self.product_id.uom_id.category_id.id
        ):
            price_unit = self.price_unit
            if self.discount:
                price_unit = price_unit * (1 - self.discount / 100)
            if self.taxes_id:
                qty = self.product_qty or 1
                price_unit = self.taxes_id.with_context(
                    round=False, round_base=False
                ).compute_all(
                    price_unit,
                    currency=self.order_id.currency_id,
                    quantity=qty,
                    product=self.product_id,
                )["total_void"]
                price_unit = price_unit / qty
            return price_unit
        return super()._get_gross_price_unit()

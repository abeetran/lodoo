from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class OrderShortageWizard(models.TransientModel):
    _name = "set_top_menu.order.shortage.wizard"
    _description = "Yêu cầu mua hàng khi thiếu tồn kho"

    order_id = fields.Many2one(
        "sale.order", string="Đơn hàng", required=True, readonly=True
    )
    message = fields.Text(string="Chi tiết thiếu hàng", readonly=True)

    def action_confirm_purchase(self):
        self.ensure_one()
        order = self.order_id
        company = order.company_id
        commands = []
        for product, vals in order._order_product_stock().items():
            rounding = product.uom_id.rounding or 0.01
            if (
                float_compare(vals["shortage"], 0.0, precision_rounding=rounding)
                <= 0
            ):
                continue
            product_company = product.with_company(company)
            po_uom = product_company.uom_po_id
            commands.append(
                [
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": product_company.display_name,
                        "product_qty": product.uom_id._compute_quantity(
                            vals["shortage"], po_uom
                        ),
                        "product_uom": po_uom.id,
                        "price_unit": product_company.standard_price,
                        "date_planned": fields.Datetime.now(),
                    },
                ]
            )
        if not commands:
            raise UserError(
                "Tồn kho đã đủ cho đơn hàng, vui lòng bấm Chuẩn bị lại."
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Mua hàng",
            "res_model": "purchase.order",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_company_id": company.id,
                "default_origin": order.catering_reference or False,
                "default_order_line": commands,
            },
        }

from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    catering_generated = fields.Boolean(
        string="Dòng tự sinh từ đơn hàng", default=False, copy=False
    )

    def _replenish_managed_food(self):
        for move in self:
            if move.location_dest_id.usage != "internal":
                continue
            product = move.product_id.with_company(move.company_id)
            quantity = move.product_uom._compute_quantity(
                move.quantity, product.uom_id, raise_if_failure=False
            )
            self.env["stock.quant"]._update_available_quantity(
                product, move.location_dest_id, quantity
            )

    def _action_done(self, cancel_backorder=False):
        todo = self.filtered(
            lambda move: move.state not in ("done", "cancel")
            and move.purchase_line_id
            and move.product_id.type == "consu"
        )
        result = super()._action_done(cancel_backorder=cancel_backorder)
        todo.filtered(lambda move: move.state == "done")._replenish_managed_food()
        return result

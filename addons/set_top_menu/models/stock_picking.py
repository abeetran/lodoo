from odoo import api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    is_delivering = fields.Boolean(
        string="Đang giao hàng", default=False, copy=False
    )
    state = fields.Selection(
        selection_add=[("delivering", "Đang giao hàng")],
        ondelete={"delivering": "set assigned"},
    )

    @api.model
    def _setup_complete(self):
        super()._setup_complete()
        # Thanh trạng thái xếp theo thứ tự selection, đưa Đang giao
        # hàng về trước Hoàn tất (selection_add luôn gắn ở cuối).
        field = self._fields["state"]
        pairs = list(field.selection)
        delivering = [pair for pair in pairs if pair[0] == "delivering"]
        if delivering:
            rest = [pair for pair in pairs if pair[0] != "delivering"]
            done_idx = next(
                (
                    index
                    for index, pair in enumerate(rest)
                    if pair[0] == "done"
                ),
                len(rest),
            )
            field.selection = rest[:done_idx] + delivering + rest[done_idx:]

    @api.depends(
        "move_type",
        "move_ids.state",
        "move_ids.picking_id",
        "is_delivering",
    )
    def _compute_state(self):
        super()._compute_state()
        for picking in self:
            if picking.is_delivering and picking.state == "assigned":
                picking.state = "delivering"

    def action_cancel(self):
        self.write({"is_delivering": False})
        return super().action_cancel()

    def button_validate(self):
        to_deliver = self.filtered(
            lambda picking: picking.state == "assigned"
            and not picking.is_delivering
            and picking.picking_type_id.code in ("outgoing", "internal")
        )
        missing = to_deliver.filtered(lambda picking: not picking.user_id)
        if missing:
            raise UserError(
                "Vui lòng gán Người phụ trách cho %s trước khi giao hàng."
                % ", ".join(missing.mapped("name"))
            )
        rest = self - to_deliver
        was_delivering = rest.filtered(
            lambda picking: picking.state == "delivering"
        )
        result = True
        if rest:
            result = super(StockPicking, rest).button_validate()
        to_deliver.write({"is_delivering": True})
        to_deliver.mapped("sale_id").filtered(
            lambda order: order.catering_state not in ("cancelled", "delivered")
        ).write({"catering_state": "dispatched"})
        for picking in was_delivering.filtered(
            lambda item: item.state == "done"
        ):
            order = picking.sale_id
            if order and order.catering_state != "cancelled":
                order.catering_state = "delivered"
        return result

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    is_delivering = fields.Boolean(
        string="Đang giao hàng", default=False, copy=False
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Đơn hàng liên kết",
        help="Chọn một đơn hàng Đang chuẩn bị theo Liên hệ để sinh "
        "dòng giao, ghi Chứng từ gốc và cập nhật trạng thái khi giao hàng.",
    )
    catering_sale_amount = fields.Float(
        string="Tổng tiền đơn liên kết (VND)",
        compute="_compute_catering_sale_amount",
        store=True,
        help="Tổng tiền VND của các đơn liên kết phiếu (mỗi đơn tính "
        "một lần) để cộng dồn lên ô dashboard.",
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

    def _sync_origin_from_sale_order(self):
        for picking in self:
            picking.origin = (
                picking.sale_order_id.catering_reference or False
            )

    @api.depends(
        "sale_id.catering_amount_vnd",
        "sale_order_id.catering_amount_vnd",
    )
    def _compute_catering_sale_amount(self):
        for picking in self:
            picking.catering_sale_amount = sum(
                (picking.sale_id | picking.sale_order_id).mapped(
                    "catering_amount_vnd"
                ),
                0.0,
            )

    def _sync_sale_order_moves(self):
        """Sinh lại dòng giao theo chi tiết còn phải giao của đơn đã chọn.

        Xóa các dòng tự sinh trước đó; bỏ qua dòng đơn đã có sẵn trên
        phiếu (tránh trùng khi chọn đúng đơn của phiếu) và dòng dịch vụ.
        Phiếu đã hoàn tất/hủy thì giữ nguyên dòng.
        """
        for picking in self:
            if picking.state in ("done", "cancel"):
                continue
            commands = [
                Command.delete(move.id)
                for move in picking.move_ids.filtered("catering_generated")
            ]
            order = picking.sale_order_id
            if order:
                covered = set(
                    picking.move_ids.filtered(
                        lambda move: not move.catering_generated
                    ).mapped("sale_line_id").ids
                )
                for line in order.order_line.filtered(
                    lambda item: not item.display_type
                    and item.product_id
                    and item.product_id.type in ("product", "consu")
                    and item.id not in covered
                ):
                    rounding = (
                        line.product_uom or line.product_id.uom_id
                    ).rounding or 0.01
                    if (
                        float_compare(
                            line.product_uom_qty,
                            line.qty_delivered,
                            precision_rounding=rounding,
                        )
                        <= 0
                    ):
                        continue
                    commands.append(
                        Command.create(
                            {
                                "name": (
                                    line.name
                                    or line.product_id.display_name
                                ),
                                "product_id": line.product_id.id,
                                "product_uom_qty": (
                                    line.product_uom_qty - line.qty_delivered
                                ),
                                "product_uom": (
                                    line.product_uom
                                    or line.product_id.uom_id
                                ).id,
                                "location_id": picking.location_id.id,
                                "location_dest_id": picking.location_dest_id.id,
                                "sale_line_id": line.id,
                                "group_id": (
                                    order.procurement_group_id.id or False
                                ),
                                "company_id": picking.company_id.id,
                                "catering_generated": True,
                            }
                        )
                    )
            if commands:
                picking.move_ids = commands

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        self._sync_origin_from_sale_order()
        self._sync_sale_order_moves()
        return self._sale_order_empty_grid_warning()

    def _sale_order_empty_grid_warning(self):
        """Cảnh báo khi đã chọn đơn mà lưới chưa có dòng nào của đơn."""
        for picking in self:
            order = picking.sale_order_id
            if (
                not order
                or picking.state in ("done", "cancel")
                or set(order.order_line.ids)
                & set(picking.move_ids.mapped("sale_line_id").ids)
            ):
                continue
            return {
                "warning": {
                    "title": "Chưa sinh được dòng giao",
                    "message": "Đơn %s: %s"
                    % (
                        order.catering_reference,
                        picking._sale_order_skip_summary(order),
                    ),
                }
            }
        return None

    def _sale_order_skip_summary(self, order):
        """Tóm tắt lý do các dòng đơn không sinh được dòng giao."""
        details = order.order_line.filtered(
            lambda line: not line.display_type
        )
        if not details:
            return "đơn chưa có dòng chi tiết nào."
        stockable = details.filtered(
            lambda line: line.product_id
            and line.product_id.type in ("product", "consu")
        )
        reasons = []
        skipped_service = len(details) - len(stockable)
        if skipped_service:
            reasons.append(
                "%d dòng là dịch vụ/không kho, không tạo dòng giao"
                % skipped_service
            )
        delivered = 0
        for line in stockable:
            rounding = (
                line.product_uom or line.product_id.uom_id
            ).rounding or 0.01
            if (
                float_compare(
                    line.product_uom_qty,
                    line.qty_delivered,
                    precision_rounding=rounding,
                )
                <= 0
            ):
                delivered += 1
        if delivered:
            reasons.append("%d dòng đã giao đủ" % delivered)
        if not reasons:
            return "không còn dòng nào cần giao."
        return "không sinh được dòng nào (%s)." % "; ".join(reasons)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            if "sale_order_id" in vals:
                record._sync_origin_from_sale_order()
                record._sync_sale_order_moves()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "sale_order_id" in vals:
            self._sync_origin_from_sale_order()
            self._sync_sale_order_moves()
        return result

    def action_cancel(self):
        self.write({"is_delivering": False})
        result = super().action_cancel()
        self._return_preparation_stock()
        return result

    def unlink(self):
        orders = self.mapped("sale_id") | self.mapped("sale_order_id")
        result = super().unlink()
        orders._preparation_stock_returnable()._return_order_stock()
        return result

    def _return_preparation_stock(self):
        """Hoàn tồn đã trừ lúc Chuẩn bị của các đơn liên quan phiếu."""
        (
            self.mapped("sale_id") | self.mapped("sale_order_id")
        )._preparation_stock_returnable()._return_order_stock()

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
        (
            to_deliver.mapped("sale_id")
            | to_deliver.mapped("sale_order_id")
        ).filtered(
            lambda order: order.catering_state
            not in ("cancelled", "delivered", "returned")
        ).write({"catering_state": "dispatched"})
        for picking in was_delivering.filtered(
            lambda item: item.state == "done"
        ):
            (
                picking.sale_id | picking.sale_order_id
            ).filtered(
                lambda order: order.catering_state
                not in ("cancelled", "returned")
            ).write({"catering_state": "delivered"})
        return result

from markupsafe import escape

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
        help="Chọn một đơn hàng Đang chuẩn bị hoặc Đã giao còn thiếu "
        "theo Liên hệ để sinh dòng giao, ghi Chứng từ gốc và cập nhật "
        "trạng thái khi giao hàng.",
    )
    purchase_order_id = fields.Many2one(
        "purchase.order",
        string="Đơn mua liên kết",
        help="Chọn một đơn mua còn thiếu hàng theo Liên hệ để sinh "
        "dòng nhập và ghi Chứng từ gốc.",
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

        Ghi vào ``move_ids_without_package`` vì đó mới là trường lưới
        Hoạt động trên form chuẩn đang gắn (ghi ``move_ids`` thì client
        không thấy, lưới không cập nhật khi chọn đơn). Xóa các dòng tự
        sinh trước đó; bỏ qua dòng đơn đã có sẵn trên phiếu (tránh trùng
        khi chọn đúng đơn của phiếu) và dòng dịch vụ. Phiếu đã hoàn
        tất/hủy thì giữ nguyên dòng.
        """
        for picking in self:
            if picking.state in ("done", "cancel"):
                continue
            grid_moves = picking.move_ids_without_package
            commands = [
                Command.delete(move.id)
                for move in grid_moves.filtered("catering_generated")
            ]
            order = picking.sale_order_id
            if order:
                covered = set(
                    (picking.move_ids | grid_moves).filtered(
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
                picking.move_ids_without_package = commands

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        self._sync_origin_from_sale_order()
        self._sync_sale_order_moves()
        return self._sale_order_empty_grid_warning()

    def _sale_order_empty_grid_warning(self):
        """Cảnh báo khi đã chọn đơn mà lưới chưa có dòng nào của đơn.

        Đọc đúng trường lưới form đang gắn (``move_ids_without_package``)
        để không báo sai khi dòng vừa sinh còn nằm ở cache chưa lưu.
        """
        for picking in self:
            order = picking.sale_order_id
            shown = set(
                (picking.move_ids | picking.move_ids_without_package)
                .mapped("sale_line_id")
                .ids
            )
            if (
                not order
                or picking.state in ("done", "cancel")
                or set(order.order_line.ids) & shown
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

    def _vals_keep_generated_rows(self, vals, line_field):
        """True khi vals còn lệnh giữ/tạo dòng tự sinh của đơn liên kết.

        Đây là tín hiệu phân biệt duy nhất giữa "client rớt M2O lúc lưu"
        (dòng tự sinh vẫn được gửi lên qua lệnh tạo/giữ) và "xóa thật"
        (client đã xóa dòng nên chỉ còn lệnh xóa 2/3/5, hoặc write ORM
        chỉ mang M2O rỗng mà không kèm lệnh dòng nào). write() dùng tín
        hiệu này để quyết định có phục hồi liên kết hay không.
        """
        move_model = self.env["stock.move"]
        for field_name in ("move_ids", "move_ids_without_package"):
            for command in vals.get(field_name) or []:
                if not command:
                    continue
                operation = command[0]
                if operation == 0:
                    data = command[2] if len(command) > 2 else {}
                    if (data or {}).get("catering_generated") and (
                        data or {}
                    ).get(line_field):
                        return True
                elif operation == 1:
                    data = command[2] if len(command) > 2 else {}
                    move = (
                        move_model.browse(command[1])
                        if len(command) > 1
                        else move_model
                    )
                    if (data or {}).get("catering_generated"):
                        if move.exists() and move[line_field]:
                            return True
                    elif (
                        move.exists()
                        and move.catering_generated
                        and move[line_field]
                    ):
                        return True
                elif operation == 4:
                    move = (
                        move_model.browse(command[1])
                        if len(command) > 1
                        else move_model
                    )
                    if (
                        move.exists()
                        and move.catering_generated
                        and move[line_field]
                    ):
                        return True
                elif operation == 6:
                    ids = command[2] if len(command) > 2 else []
                    moves = move_model.browse(ids or [])
                    if any(
                        move.catering_generated and move[line_field]
                        for move in moves
                    ):
                        return True
        return False

    def _recover_cleared_sale_order(self):
        """Phục hồi đơn liên kết khi client mất giá trị M2O lúc lưu.

        Chỉ chạy sau super().create/write khi write()/create() đã xác
        định đây là ca rớt M2O (còn dòng tự sinh được giữ lại): suy ngược
        đơn từ sale_line_id và đặt lại thay vì xóa trắng lưới + gốc.
        Không dùng trong onchange (ở đó dòng ảo chưa xóa, sẽ đánh nhau
        với thao tác xóa thật của user).
        """
        for picking in self:
            if picking.sale_order_id:
                continue
            generated = (
                picking.move_ids | picking.move_ids_without_package
            ).filtered(
                lambda move: move.catering_generated
                and move.sale_line_id
            )
            orders = generated.mapped("sale_line_id.order_id")
            if len(orders) == 1:
                super(StockPicking, picking).write(
                    {"sale_order_id": orders.id}
                )

    def _sync_header_from_purchase_order(self):
        for picking in self:
            order = picking.purchase_order_id
            picking.origin = order.name or False
            if order:
                picking.partner_id = order.partner_id

    def _sync_purchase_order_moves(self):
        """Sinh lại dòng nhập theo chi tiết còn phải nhập của đơn đã chọn.

        Cùng mẫu đơn bán: ghi vào trường lưới form đang gắn, xóa các
        dòng tự sinh trước đó, bỏ qua dòng đã có sẵn trên phiếu và dòng
        dịch vụ. Phiếu đã hoàn tất/hủy thì giữ nguyên dòng.
        """
        for picking in self:
            if picking.state in ("done", "cancel"):
                continue
            grid_moves = picking.move_ids_without_package
            commands = [
                Command.delete(move.id)
                for move in grid_moves.filtered("catering_generated")
            ]
            order = picking.purchase_order_id
            if order:
                covered = set(
                    (picking.move_ids | grid_moves).filtered(
                        lambda move: not move.catering_generated
                    ).mapped("purchase_line_id").ids
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
                            line.product_qty,
                            line.qty_received,
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
                                    line.product_qty - line.qty_received
                                ),
                                "product_uom": (
                                    line.product_uom
                                    or line.product_id.uom_id
                                ).id,
                                "location_id": picking.location_id.id,
                                "location_dest_id": picking.location_dest_id.id,
                                "purchase_line_id": line.id,
                                "company_id": picking.company_id.id,
                                "catering_generated": True,
                            }
                        )
                    )
            if commands:
                picking.move_ids_without_package = commands

    @api.onchange("purchase_order_id")
    def _onchange_purchase_order_id(self):
        self._sync_header_from_purchase_order()
        self._sync_purchase_order_moves()
        return self._purchase_order_empty_grid_warning()

    def _purchase_order_empty_grid_warning(self):
        """Cảnh báo khi đã chọn đơn mua mà lưới chưa có dòng nào."""
        for picking in self:
            order = picking.purchase_order_id
            shown = set(
                (picking.move_ids | picking.move_ids_without_package)
                .mapped("purchase_line_id")
                .ids
            )
            if (
                not order
                or picking.state in ("done", "cancel")
                or set(order.order_line.ids) & shown
            ):
                continue
            return {
                "warning": {
                    "title": "Chưa sinh được dòng nhập",
                    "message": "Đơn %s: %s"
                    % (
                        order.name,
                        picking._purchase_order_skip_summary(order),
                    ),
                }
            }
        return None

    def _purchase_order_skip_summary(self, order):
        """Tóm tắt lý do các dòng mua không sinh được dòng nhập."""
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
                "%d dòng là dịch vụ/không kho, không tạo dòng nhập"
                % skipped_service
            )
        received = 0
        for line in stockable:
            rounding = (
                line.product_uom or line.product_id.uom_id
            ).rounding or 0.01
            if (
                float_compare(
                    line.product_qty,
                    line.qty_received,
                    precision_rounding=rounding,
                )
                <= 0
            ):
                received += 1
        if received:
            reasons.append("%d dòng đã nhập đủ" % received)
        if not reasons:
            return "không còn dòng nào cần nhập."
        return "không sinh được dòng nào (%s)." % "; ".join(reasons)

    def _recover_cleared_purchase_order(self):
        """Phục hồi đơn mua liên kết khi client mất giá trị M2O lúc lưu.

        Cùng mẫu phía đơn bán: sau super().create/write mà M2O trống
        nhưng còn dòng tự sinh được giữ lại (write()/create() đã kiểm tra
        tín hiệu lệnh dòng) thì suy ngược đơn mua từ purchase_line_id
        và đặt lại. Không dùng trong onchange.
        """
        for picking in self:
            if picking.purchase_order_id:
                continue
            generated = (
                picking.move_ids | picking.move_ids_without_package
            ).filtered(
                lambda move: move.catering_generated
                and move.purchase_line_id
            )
            orders = generated.mapped("purchase_line_id.order_id")
            if len(orders) == 1:
                super(StockPicking, picking).write(
                    {"purchase_order_id": orders.id}
                )

    def _log_sale_delivery_done(self):
        """Ghi lịch sử giao bù vào Hoạt động của đơn hàng liên kết."""
        for picking in self:
            order = picking.sale_order_id
            if not order:
                continue
            lines = [
                "- %s: %s %s"
                % (
                    escape(move.product_id.display_name),
                    "%g" % move.quantity,
                    escape(move.product_uom.display_name),
                )
                for move in picking.move_ids
            ]
            body = "Giao bổ sung từ phiếu giao %s:<br/>%s" % (
                escape(picking.name),
                "<br/>".join(lines) if lines else "Không có dòng nào.",
            )
            order.message_post(body=body, subtype_xmlid="mail.mt_note")

    def _log_purchase_receipt_done(self):
        """Ghi lịch sử nhập bổ sung vào Hoạt động của đơn mua liên kết."""
        for picking in self:
            order = picking.purchase_order_id
            if not order:
                continue
            lines = [
                "- %s: %s %s"
                % (
                    escape(move.product_id.display_name),
                    "%g" % move.quantity,
                    escape(move.product_uom.display_name),
                )
                for move in picking.move_ids
            ]
            body = "Nhập bổ sung từ phiếu nhập %s:<br/>%s" % (
                escape(picking.name),
                "<br/>".join(lines) if lines else "Không có dòng nào.",
            )
            order.message_post(body=body, subtype_xmlid="mail.mt_note")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Phiếu mới có dòng tự sinh mà mất liên kết thì chắc chắn là
        # client rớt M2O (phiếu mới không có gì để "xóa thật"): phục hồi
        # trước rồi mới đồng bộ, kể cả khi vals thiếu hẳn key liên kết.
        records._recover_cleared_sale_order()
        records._recover_cleared_purchase_order()
        for record, vals in zip(records, vals_list):
            if "sale_order_id" in vals or record.sale_order_id:
                record._sync_origin_from_sale_order()
                record._sync_sale_order_moves()
            if "purchase_order_id" in vals or record.purchase_order_id:
                record._sync_header_from_purchase_order()
                record._sync_purchase_order_moves()
        return records

    def write(self, vals):
        # Chỉ phục hồi khi vals còn lệnh giữ dòng tự sinh (tín hiệu rớt
        # M2O của client). write chỉ mang M2O rỗng, hoặc kèm toàn lệnh
        # xóa dòng, là xóa thật → để sync xóa trắng như cũ.
        recover_sale = (
            "sale_order_id" in vals
            and not vals["sale_order_id"]
            and self._vals_keep_generated_rows(vals, "sale_line_id")
        )
        recover_purchase = (
            "purchase_order_id" in vals
            and not vals["purchase_order_id"]
            and self._vals_keep_generated_rows(vals, "purchase_line_id")
        )
        result = super().write(vals)
        if "sale_order_id" in vals:
            if recover_sale:
                self._recover_cleared_sale_order()
            self._sync_origin_from_sale_order()
            self._sync_sale_order_moves()
        if "purchase_order_id" in vals:
            if recover_purchase:
                self._recover_cleared_purchase_order()
            self._sync_header_from_purchase_order()
            self._sync_purchase_order_moves()
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
        # Lượng trừ lúc Chuẩn bị chỉ là giữ chỗ: trước khi lõi trừ kho
        # thật lúc hoàn tất, hoàn lại phần giữ chỗ để mỗi hàng chỉ trừ
        # đúng một lần. Bỏ qua phiếu đã xong/hủy để không cộng kho oan.
        validating = rest.filtered(
            lambda picking: picking.state not in ("done", "cancel")
        )
        (
            validating.mapped("sale_id")
            | validating.mapped("sale_order_id")
        )._preparation_stock_returnable()._return_order_stock()
        was_delivering = rest.filtered(
            lambda picking: picking.state == "delivering"
        )
        was_receiving = rest.filtered(
            lambda picking: picking.purchase_order_id
            and picking.state not in ("done", "cancel")
        )
        was_sale_linked = rest.filtered(
            lambda picking: picking.sale_order_id
            and picking.state not in ("done", "cancel")
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
        for picking in was_receiving.filtered(
            lambda item: item.state == "done"
        ):
            picking._log_purchase_receipt_done()
        for picking in was_sale_linked.filtered(
            lambda item: item.state == "done"
        ):
            picking._log_sale_delivery_done()
        return result

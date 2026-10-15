from markupsafe import escape

from odoo import fields, models
from odoo.exceptions import UserError


class OrderCancelWizard(models.TransientModel):
    _name = "set_top_menu.order.cancel.wizard"
    _description = "Lý do huỷ đơn hàng"

    order_id = fields.Many2one(
        "sale.order", string="Đơn hàng", required=True, readonly=True
    )
    reason = fields.Text(string="Lý do huỷ đơn")

    def _require_reason(self):
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError("Vui lòng nhập lý do huỷ đơn.")
        return reason

    def action_confirm_cancel(self):
        """Xác nhận huỷ đơn: bắt buộc lý do, ghi vào hoạt động.

        Đi qua ``action_cancel`` để trạng thái lõi Odoo cũng về
        ``cancel`` (lõi chặn xóa đơn còn ở ``sale``), lý do theo
        context để log hoạt động giữ nguyên.
        """
        self.ensure_one()
        reason = self._require_reason()
        order = self.order_id
        order._check_cancel_allowed()
        order.with_context(cancel_reason=reason).action_cancel()
        return {"type": "ir.actions.act_window_close"}

    def action_discard_cancel(self):
        """Huỷ bỏ thao tác: lý do đã nhập vẫn lưu vào hoạt động."""
        self.ensure_one()
        reason = (self.reason or "").strip()
        if reason:
            self.order_id.message_post(
                body="Thao tác huỷ đơn đã bị huỷ bỏ. Lý do đã nhập: %s."
                % escape(reason).replace("\n", "<br/>"),
                subtype_xmlid="mail.mt_note",
            )
        return {"type": "ir.actions.act_window_close"}

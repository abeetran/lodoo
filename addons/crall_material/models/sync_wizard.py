from odoo import _, fields, models
from odoo.exceptions import UserError


class CrallMaterialSyncWizard(models.TransientModel):
    _name = "crall.material.sync.wizard"
    _description = "Crall Material Synchronization"

    token = fields.Char(
        string="Bearer token",
        password=True,
        required=True,
    )
    page = fields.Integer(string="Page", default=1, required=True)

    def action_sync_sub_suppliers(self):
        self.ensure_one()
        if self.page < 1:
            raise UserError(_("Số trang phải lớn hơn hoặc bằng 1."))
        result = self.env["res.partner"].sync_crall_sub_suppliers(
            token=self.token,
            page=self.page,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": "Sub-suppliers page %s: %s created, %s updated, %s skipped"
                % (
                    self.page,
                    result["created"],
                    result["updated"],
                    result["skipped"],
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_schools(self):
        self.ensure_one()
        if self.page < 1:
            raise UserError(_("Số trang phải lớn hơn hoặc bằng 1."))
        result = self.env["res.partner"].sync_crall_schools(
            token=self.token,
            page=self.page,
            per_page=15,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": "Trường học trang %s (15/trang): %s created, %s updated, %s skipped"
                % (
                    self.page,
                    result["created"],
                    result["updated"],
                    result["skipped"],
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def _notify_result(self, message, has_changes):
        # Ở yên màn hình Data Sync, chỉ hiện thông báo (không điều hướng).
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": message,
                "type": "success" if has_changes else "warning",
                "sticky": False,
            },
        }

    def action_sync_foods(self):
        self.ensure_one()
        if self.page < 1:
            raise UserError(_("Số trang phải lớn hơn hoặc bằng 1."))
        result = self.env["product.template"].sync_crall_foods(
            token=self.token,
            page=self.page,
            page_size=15,
        )
        return self._notify_result(
            _("Thực phẩm trang %s (15/trang): %s mới, %s cập nhật, %s bỏ qua. "
              "Mở menu Thực phẩm để xem danh sách.")
            % (self.page, result["created"], result["updated"], result["skipped"]),
            bool(result["created"] or result["updated"]),
        )

    def action_sync_foods_all(self):
        self.ensure_one()
        result = self.env["product.template"].sync_crall_foods_all(
            token=self.token,
            page_size=15,
        )
        return self._notify_result(
            _("Thực phẩm %s trang (15/trang): %s mới, %s cập nhật, %s bỏ qua. "
              "Mở menu Thực phẩm để xem danh sách.")
            % (
                result["pages"],
                result["created"],
                result["updated"],
                result["skipped"],
            ),
            bool(result["created"] or result["updated"]),
        )

    def action_sync_supplier_steps(self):
        self.ensure_one()
        if self.page < 1:
            raise UserError(_("Số trang phải lớn hơn hoặc bằng 1."))
        result = self.env["set_top_menu.production.step"].sync_supplier_steps(
            token=self.token,
            page=self.page,
            per_page=15,
        )
        return self._notify_result(
            _("Khâu sản xuất trang %s (15/trang): %s mới, %s cập nhật, %s bỏ qua. "
              "Mở menu QL khâu SX để xem danh sách.")
            % (self.page, result["created"], result["updated"], result["skipped"]),
            bool(result["created"] or result["updated"]),
        )

    def action_sync_supplier_processes(self):
        self.ensure_one()
        if self.page < 1:
            raise UserError(_("Số trang phải lớn hơn hoặc bằng 1."))
        result = self.env["set_top_menu.production.process"].sync_supplier_processes(
            token=self.token,
            page=self.page,
            per_page=15,
        )
        return self._notify_result(
            _("Quy trình SX trang %s (15/trang): %s mới, %s cập nhật, %s bỏ qua. "
              "Mở menu QL Quy trình SX để xem danh sách.")
            % (self.page, result["created"], result["updated"], result["skipped"]),
            bool(result["created"] or result["updated"]),
        )

    def action_sync(self):
        self.ensure_one()
        if self.page < 1:
            raise UserError(_("Số trang phải lớn hơn hoặc bằng 1."))
        result = self.env["product.template"].sync_crall_materials(
            token=self.token,
            page=self.page,
        )
        return self._notify_result(
            _("Thực phẩm chuẩn trang %s: %s mới, %s cập nhật, %s bỏ qua. "
              "Mở menu Thực phẩm để xem danh sách.")
            % (self.page, result["created"], result["updated"], result["skipped"]),
            bool(result["created"] or result["updated"]),
        )
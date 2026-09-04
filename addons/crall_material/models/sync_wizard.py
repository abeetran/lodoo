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

    def action_sync(self):
        self.ensure_one()
        if self.page < 1:
            raise UserError(_("Số trang phải lớn hơn hoặc bằng 1."))
        result = self.env["product.template"].sync_crall_materials(
            token=self.token,
            page=self.page,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": "Page %s: %s created, %s skipped"
                % (self.page, result["created"], result["skipped"]),
                "type": "success",
                "sticky": False,
            },
        }
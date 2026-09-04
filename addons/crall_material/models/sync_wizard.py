from odoo import fields, models


class CrallMaterialSyncWizard(models.TransientModel):
    _name = "crall.material.sync.wizard"
    _description = "Crall Material Synchronization"

    token = fields.Char(
        string="Bearer token",
        password=True,
        required=True,
    )

    def action_sync(self):
        self.ensure_one()
        result = self.env["product.template"].sync_crall_materials(token=self.token)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": "%s created, %s updated"
                % (result["created"], result["updated"]),
                "type": "success",
                "sticky": False,
            },
        }
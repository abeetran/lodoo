from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    crall_supplier_api_url = fields.Char(
        string="Supplier API URL",
        config_parameter="crall_material.supplier_api_url",
        default="https://ncc-api.hanoicheck.com.vn/supplier/standard-foods",
    )
    crall_supplier_api_token = fields.Char(
        string="Supplier API token",
        config_parameter="crall_material.supplier_api_token",
        password=True,
    )
    crall_supplier_api_referer = fields.Char(
        string="Supplier API referer",
        config_parameter="crall_material.supplier_api_referer",
        default="https://ncc.hanoicheck.com.vn",
    )

    def action_sync_crall_materials(self):
        self.ensure_one()
        self.set_values()
        self.env["product.template"].sync_crall_materials(
            url=self.crall_supplier_api_url,
            token=self.crall_supplier_api_token,
            referer=self.crall_supplier_api_referer,
        )
        return {"type": "ir.actions.client", "tag": "reload"}
from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    authentik_enabled = fields.Boolean(string="Enable Authentik SSO")

    authentik_base_url = fields.Char(string="Authentik Base URL")
    authentik_client_id = fields.Char(string="Authentik Client ID")
    authentik_client_secret = fields.Char(string="Authentik Client Secret")

    authentik_scope = fields.Char(string="OIDC Scope", default="openid profile email")
    authentik_auto_create_user = fields.Boolean(string="Auto-create user on first login", default=True)

    authentik_allowed_domain = fields.Char(
        string="Allowed Email Domain (optional)",
        help="Example: company.com . If set, only emails in this domain can login."
    )

    def set_values(self):
        super().set_values()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("authentik.enabled", self.authentik_enabled)

        ICP.set_param("authentik.base_url", (self.authentik_base_url or "").rstrip("/"))
        ICP.set_param("authentik.client_id", self.authentik_client_id or "")
        ICP.set_param("authentik.client_secret", self.authentik_client_secret or "")

        ICP.set_param("authentik.scope", self.authentik_scope or "openid profile email")
        ICP.set_param("authentik.auto_create_user", self.authentik_auto_create_user)
        ICP.set_param("authentik.allowed_domain", self.authentik_allowed_domain or "")

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env["ir.config_parameter"].sudo()

        res.update(
            authentik_enabled=ICP.get_param("authentik.enabled") in ("True", "1", True),

            authentik_base_url=ICP.get_param("authentik.base_url", default=""),
            authentik_client_id=ICP.get_param("authentik.client_id", default=""),
            authentik_client_secret=ICP.get_param("authentik.client_secret", default=""),

            authentik_scope=ICP.get_param("authentik.scope", default="openid profile email"),
            authentik_auto_create_user=ICP.get_param("authentik.auto_create_user") in ("True", "1", True),
            authentik_allowed_domain=ICP.get_param("authentik.allowed_domain", default=""),
        )
        return res

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    chatwoot_base_url = fields.Char(string="Chatwoot Base URL")
    chatwoot_account_id = fields.Char(string="Chatwoot Account ID")
    chatwoot_api_access_token = fields.Char(string="Chatwoot API Access Token")
    chatwoot_inbox_id = fields.Char(string="Chatwoot Inbox ID")
    chatwoot_inbox_identifier = fields.Char(string="Chatwoot Inbox Identifier")
    chatwoot_webhook_secret = fields.Char(string="Webhook Secret")
    chatwoot_auto_create_lead = fields.Boolean(string="Auto-create CRM Lead from webhook", default=True)

    def set_values(self):
        super().set_values()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("chatwoot.base_url", (self.chatwoot_base_url or "").rstrip("/"))
        ICP.set_param("chatwoot.account_id", self.chatwoot_account_id or "")
        ICP.set_param("chatwoot.api_access_token", self.chatwoot_api_access_token or "")
        ICP.set_param("chatwoot.inbox_id", self.chatwoot_inbox_id or "")
        ICP.set_param("chatwoot.inbox_identifier", self.chatwoot_inbox_identifier or "")
        ICP.set_param("chatwoot.webhook_secret", self.chatwoot_webhook_secret or "")
        ICP.set_param("chatwoot.auto_create_lead", self.chatwoot_auto_create_lead)

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env["ir.config_parameter"].sudo()
        res.update(
            chatwoot_base_url=ICP.get_param("chatwoot.base_url", default="https://omnichat.zflux.cloud"),
            chatwoot_account_id=ICP.get_param("chatwoot.account_id", default=""),
            chatwoot_api_access_token=ICP.get_param("chatwoot.api_access_token", default=""),
            chatwoot_inbox_id=ICP.get_param("chatwoot.inbox_id", default=""),
            chatwoot_inbox_identifier=ICP.get_param("chatwoot.inbox_identifier", default=""),
            chatwoot_webhook_secret=ICP.get_param("chatwoot.webhook_secret", default=""),
            chatwoot_auto_create_lead=ICP.get_param("chatwoot.auto_create_lead", default="1") in ("True", "1", True),
        )
        return res

# -*- coding: utf-8 -*-
import json
import logging

from markupsafe import Markup, escape

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _cfg(key, default=""):
    return request.env["ir.config_parameter"].sudo().get_param(key, default=default)


class ChatwootCRMWebhookController(http.Controller):
    @http.route("/chatwoot/webhook", type="http", auth="none", csrf=False, methods=["POST"])
    def chatwoot_webhook(self, **kw):
        secret = (_cfg("chatwoot.webhook_secret") or "").strip()
        if secret:
            incoming = (
                request.httprequest.headers.get("X-Chatwoot-Webhook-Secret")
                or request.httprequest.headers.get("x-chatwoot-webhook-secret")
                or kw.get("secret")
                or ""
            )
            if incoming != secret:
                return request.make_json_response({"ok": False, "error": "invalid secret"}, status=403)

        try:
            payload = request.httprequest.get_json(silent=True) or json.loads(
                request.httprequest.data.decode("utf-8") or "{}"
            )
        except Exception:
            _logger.exception("Invalid Chatwoot webhook payload")
            return request.make_json_response({"ok": False, "error": "invalid payload"}, status=400)

        event = payload.get("event")
        if event not in ("conversation_created", "conversation_status_changed", "message_created"):
            return request.make_json_response({"ok": True, "ignored": event})

        lead = self._find_lead(payload)
        if not lead:
            lead = self._create_lead_from_payload(payload)

        if lead:
            self._sync_lead_fields(lead, payload)
            if event == "message_created":
                self._post_message(lead, payload)
            elif event == "conversation_created":
                lead.message_post(body=Markup("<b>Chatwoot</b>: Conversation created."))
            elif event == "conversation_status_changed":
                status = payload.get("status") or (payload.get("conversation") or {}).get("status") or "unknown"
                lead.message_post(body=Markup("<b>Chatwoot</b>: Conversation status changed to %s.") % escape(status))

        return request.make_json_response({"ok": True, "event": event, "lead_id": lead.id if lead else False})

    def _find_lead(self, payload):
        Lead = request.env["crm.lead"].sudo()
        conversation = payload.get("conversation") or {}
        contact = payload.get("contact") or (payload.get("meta") or {}).get("sender") or payload.get("sender") or {}

        conversation_id = str(conversation.get("id") or payload.get("conversation_id") or payload.get("id") or "")
        contact_id = str(contact.get("id") or "")
        email = (contact.get("email") or "").strip()
        phone = (contact.get("phone_number") or contact.get("phone") or "").strip()

        if conversation_id:
            lead = Lead.search([("chatwoot_conversation_id", "=", conversation_id)], limit=1)
            if lead:
                return lead
        if contact_id:
            lead = Lead.search([("chatwoot_contact_id", "=", contact_id)], limit=1)
            if lead:
                return lead
        if email:
            lead = Lead.search(["|", ("email_from", "=", email), ("partner_id.email", "=", email)], limit=1)
            if lead:
                return lead
        if phone:
            lead = Lead.search(["|", ("phone", "=", phone), ("mobile", "=", phone)], limit=1)
            if lead:
                return lead
        return Lead.browse()

    def _create_lead_from_payload(self, payload):
        if not str(_cfg("chatwoot.auto_create_lead", "1")).lower() in ("1", "true", "yes"):
            return request.env["crm.lead"].sudo().browse()

        contact = payload.get("contact") or (payload.get("meta") or {}).get("sender") or payload.get("sender") or {}
        name = contact.get("name") or contact.get("email") or contact.get("phone_number") or "Chatwoot conversation"
        values = {
            "name": f"Chatwoot: {name}",
            "contact_name": contact.get("name") or "",
            "email_from": contact.get("email") or "",
            "phone": contact.get("phone_number") or contact.get("phone") or "",
        }
        return request.env["crm.lead"].sudo().create(values)

    def _sync_lead_fields(self, lead, payload):
        conversation = payload.get("conversation") or {}
        contact = payload.get("contact") or (payload.get("meta") or {}).get("sender") or payload.get("sender") or {}
        values = {}

        conversation_id = conversation.get("id") or payload.get("conversation_id")
        contact_id = contact.get("id")
        if conversation_id:
            values["chatwoot_conversation_id"] = str(conversation_id)
        if contact_id:
            values["chatwoot_contact_id"] = str(contact_id)

        if values:
            lead.sudo().write(values)

    def _post_message(self, lead, payload):
        message_id = str(payload.get("id") or "")
        if message_id and lead.chatwoot_last_message_id == message_id:
            return

        sender = payload.get("sender") or {}
        sender_name = sender.get("name") or sender.get("type") or "Chatwoot"
        content = payload.get("content") or payload.get("processed_message_content") or ""
        message_type = payload.get("message_type")

        body = Markup("<b>Chatwoot message</b><br/>")
        body += Markup("From: %s<br/>") % escape(sender_name)
        if message_type is not None:
            body += Markup("Type: %s<br/>") % escape(str(message_type))
        body += Markup("<br/>%s") % escape(content or "(empty message)")

        lead.message_post(body=body)
        if message_id:
            lead.sudo().write({"chatwoot_last_message_id": message_id})

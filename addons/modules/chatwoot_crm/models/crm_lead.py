# -*- coding: utf-8 -*-
import logging
import re

import requests

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    chatwoot_contact_id = fields.Char(string="Chatwoot Contact ID", copy=False, index=True)
    chatwoot_contact_source_id = fields.Char(string="Chatwoot Contact Source ID", copy=False, index=True)
    chatwoot_conversation_id = fields.Char(string="Chatwoot Conversation ID", copy=False, index=True)
    chatwoot_last_message_id = fields.Char(string="Last Chatwoot Message ID", copy=False)
    chatwoot_url = fields.Char(string="Chatwoot URL", compute="_compute_chatwoot_url")

    def _compute_chatwoot_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("chatwoot.base_url", "").rstrip("/")
        account_id = self.env["ir.config_parameter"].sudo().get_param("chatwoot.account_id", "")
        for lead in self:
            if base_url and account_id and lead.chatwoot_conversation_id:
                lead.chatwoot_url = f"{base_url}/app/accounts/{account_id}/conversations/{lead.chatwoot_conversation_id}"
            elif base_url and account_id and lead.chatwoot_contact_id:
                lead.chatwoot_url = f"{base_url}/app/accounts/{account_id}/contacts/{lead.chatwoot_contact_id}"
            else:
                lead.chatwoot_url = False

    def action_chatwoot_sync_contact(self):
        for lead in self:
            lead._chatwoot_sync_contact()
        return self._notify("Chatwoot contact synced.")

    def action_chatwoot_create_conversation(self):
        for lead in self:
            lead._chatwoot_sync_contact()
            lead._chatwoot_create_conversation()
        return self._notify("Chatwoot conversation created.")

    def action_chatwoot_open(self):
        self.ensure_one()
        if not self.chatwoot_url:
            raise UserError("Sync the Chatwoot contact or create a conversation first.")
        return {
            "type": "ir.actions.act_url",
            "url": self.chatwoot_url,
            "target": "new",
        }

    def _chatwoot_sync_contact(self):
        self.ensure_one()
        base_url, account_id, token = self._chatwoot_required_config()
        inbox_id = self.env["ir.config_parameter"].sudo().get_param("chatwoot.inbox_id", "")

        payload = {
            "name": self.contact_name or self.partner_name or self.name,
            "email": self.email_from or (self.partner_id.email if self.partner_id else ""),
            "identifier": f"odoo-crm-lead-{self.id}",
            "custom_attributes": self._chatwoot_custom_attributes(),
        }
        phone_number = self._chatwoot_e164_phone()
        if phone_number:
            payload["phone_number"] = phone_number
        if inbox_id:
            payload["inbox_id"] = int(inbox_id)

        contact_id = self.chatwoot_contact_id
        if not contact_id:
            existing_contact = self._chatwoot_find_contact(base_url, account_id, token, payload)
            contact_id = existing_contact.get("id")

        if contact_id:
            response = self._chatwoot_request(
                "put",
                f"{base_url}/api/v1/accounts/{account_id}/contacts/{contact_id}",
                token,
                payload,
            )
        else:
            response = self._chatwoot_create_or_recover_contact(
                base_url, account_id, token, payload
            )

        contact = self._extract_payload(response)
        contact_id = contact.get("id") or contact_id or self.chatwoot_contact_id
        source_id = self._extract_source_id(contact) or self.chatwoot_contact_source_id
        if contact_id and inbox_id and not source_id:
            source_id = self._chatwoot_ensure_contact_source_id(base_url, account_id, token, contact_id, inbox_id)
        values = {}
        if contact_id:
            values["chatwoot_contact_id"] = str(contact_id)
        if source_id:
            values["chatwoot_contact_source_id"] = str(source_id)
        if values:
            self.write(values)
        self.message_post(body="Chatwoot contact synced.")
        return contact

    def _chatwoot_create_conversation(self):
        self.ensure_one()
        base_url, account_id, token = self._chatwoot_required_config()
        inbox_id = self.env["ir.config_parameter"].sudo().get_param("chatwoot.inbox_id", "")

        if self.chatwoot_conversation_id:
            return
        if not inbox_id:
            raise UserError("Configure Chatwoot Inbox ID before creating conversations.")
        if not self.chatwoot_contact_id:
            raise UserError("Chatwoot contact ID is missing. Sync the contact first.")
        if not self.chatwoot_contact_source_id:
            source_id = self._chatwoot_ensure_contact_source_id(
                base_url, account_id, token, self.chatwoot_contact_id, inbox_id
            )
            if source_id:
                self.write({"chatwoot_contact_source_id": str(source_id)})
            else:
                raise UserError("Chatwoot contact source ID is missing. Sync the contact with an inbox first.")

        response = requests.post(
            f"{base_url}/api/v1/accounts/{account_id}/conversations",
            json={
                "source_id": self.chatwoot_contact_source_id,
                "inbox_id": int(inbox_id),
                "contact_id": int(self.chatwoot_contact_id),
                "custom_attributes": self._chatwoot_custom_attributes(),
                "status": "open",
            },
            headers={"Content-Type": "application/json", "api_access_token": token},
            timeout=30,
        )
        if response.status_code >= 400:
            raise UserError(f"Chatwoot conversation error: {self._chatwoot_error_message(response)}")
        data = response.json()
        conversation_id = data.get("id")
        if conversation_id:
            self.write({"chatwoot_conversation_id": str(conversation_id)})
            self.message_post(body=f"Chatwoot conversation created: {conversation_id}")

    def _chatwoot_custom_attributes(self):
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        return {
            "odoo_lead_id": self.id,
            "odoo_lead_url": f"{base_url}/web#id={self.id}&model=crm.lead&view_type=form" if base_url else "",
            "crm_stage": self.stage_id.name or "",
            "expected_revenue": self.expected_revenue or 0,
            "salesperson": self.user_id.name or "",
        }

    def _chatwoot_e164_phone(self):
        self.ensure_one()
        raw_phone = (
            self.mobile
            or self.phone
            or (self.partner_id.mobile if self.partner_id else "")
            or (self.partner_id.phone if self.partner_id else "")
        )
        return self._chatwoot_normalize_e164(raw_phone)

    def _chatwoot_normalize_e164(self, raw_phone):
        if not raw_phone:
            return False
        phone = str(raw_phone).strip()
        phone = re.sub(r"[\s().-]", "", phone)
        if phone.startswith("00"):
            phone = "+" + phone[2:]
        elif phone.startswith("0"):
            phone = "+84" + phone[1:]
        elif phone.startswith("84"):
            phone = "+" + phone
        elif phone and phone[0].isdigit():
            return False

        if re.fullmatch(r"\+[1-9]\d{7,14}", phone):
            return phone
        return False

    def _chatwoot_required_config(self):
        ICP = self.env["ir.config_parameter"].sudo()
        base_url = ICP.get_param("chatwoot.base_url", "").rstrip("/")
        account_id = ICP.get_param("chatwoot.account_id", "")
        token = ICP.get_param("chatwoot.api_access_token", "")
        missing = []
        if not base_url:
            missing.append("Chatwoot Base URL")
        if not account_id:
            missing.append("Chatwoot Account ID")
        if not token:
            missing.append("Chatwoot API Access Token")
        if missing:
            raise UserError("Missing Chatwoot configuration: %s" % ", ".join(missing))
        return base_url, account_id, token

    def _chatwoot_request(self, method, url, token, payload=None, params=None):
        response = requests.request(
            method,
            url,
            json=payload,
            params=params,
            headers={"Content-Type": "application/json", "api_access_token": token},
            timeout=30,
        )
        if response.status_code >= 400:
            _logger.error("Chatwoot API error %s: %s", response.status_code, response.text)
            raise UserError(f"Chatwoot API error: {self._chatwoot_error_message(response)}")
        return response.json()

    def _chatwoot_create_or_recover_contact(self, base_url, account_id, token, payload):
        response = requests.post(
            f"{base_url}/api/v1/accounts/{account_id}/contacts",
            json=payload,
            headers={"Content-Type": "application/json", "api_access_token": token},
            timeout=30,
        )
        if response.status_code < 400:
            return response.json()

        existing_contact = self._chatwoot_find_contact(base_url, account_id, token, payload)
        if existing_contact.get("id"):
            return self._chatwoot_request(
                "put",
                f"{base_url}/api/v1/accounts/{account_id}/contacts/{existing_contact['id']}",
                token,
                payload,
            )

        _logger.error("Chatwoot API error %s: %s", response.status_code, response.text)
        raise UserError(f"Chatwoot API error: {self._chatwoot_error_message(response)}")

    def _chatwoot_error_message(self, response):
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.text
        message = re.sub(r"<[^>]+>", " ", response.text or "")
        message = re.sub(r"\s+", " ", message).strip()
        return message[:500] or f"HTTP {response.status_code}"

    def _chatwoot_find_contact(self, base_url, account_id, token, payload):
        terms = [
            payload.get("identifier"),
            payload.get("email"),
            payload.get("phone_number"),
        ]
        for term in [term for term in terms if term]:
            response = self._chatwoot_request(
                "get",
                f"{base_url}/api/v1/accounts/{account_id}/contacts/search",
                token,
                params={"q": term},
            )
            contact = self._chatwoot_pick_contact_match(response, payload)
            if contact:
                return contact
        return {}

    def _chatwoot_pick_contact_match(self, response, payload):
        contacts = response.get("payload") or []
        for contact in contacts:
            if payload.get("identifier") and contact.get("identifier") == payload.get("identifier"):
                return contact
        for contact in contacts:
            if payload.get("email") and contact.get("email") == payload.get("email"):
                return contact
        for contact in contacts:
            if payload.get("phone_number") and contact.get("phone_number") == payload.get("phone_number"):
                return contact
        return contacts[0] if contacts else {}

    def _extract_payload(self, response):
        payload = response.get("payload", response)
        if isinstance(payload, list):
            return payload[0] if payload else {}
        return payload or {}

    def _extract_source_id(self, contact):
        if contact.get("source_id"):
            return contact.get("source_id")
        for contact_inbox in contact.get("contact_inboxes") or []:
            source_id = contact_inbox.get("source_id")
            if source_id:
                return source_id
        return False

    def _chatwoot_get_contact_source_id(self, base_url, account_id, token, contact_id, inbox_id):
        if not contact_id or not inbox_id:
            return False
        response = requests.get(
            f"{base_url}/api/v1/accounts/{account_id}/contacts/{contact_id}/contactable_inboxes",
            headers={"api_access_token": token},
            timeout=30,
        )
        if response.status_code >= 400:
            _logger.warning("Chatwoot contactable inboxes error %s: %s", response.status_code, response.text)
            return False
        data = self._extract_payload(response.json())
        inboxes = data if isinstance(data, list) else data.get("payload", [])
        for contact_inbox in inboxes or []:
            inbox = contact_inbox.get("inbox") or {}
            if str(inbox.get("id")) == str(inbox_id):
                return contact_inbox.get("source_id")
        return False

    def _chatwoot_ensure_contact_source_id(self, base_url, account_id, token, contact_id, inbox_id):
        source_id = self._chatwoot_get_contact_source_id(base_url, account_id, token, contact_id, inbox_id)
        if source_id:
            return source_id

        generated_source_id = f"odoo-crm-lead-{self.id}"
        response = requests.post(
            f"{base_url}/api/v1/accounts/{account_id}/contacts/{contact_id}/contact_inboxes",
            json={"inbox_id": int(inbox_id), "source_id": generated_source_id},
            headers={"Content-Type": "application/json", "api_access_token": token},
            timeout=30,
        )
        if response.status_code >= 400:
            _logger.warning("Chatwoot create contact inbox error %s: %s", response.status_code, response.text)
            return self._chatwoot_get_contact_source_id(base_url, account_id, token, contact_id, inbox_id)

        contact_inbox = self._extract_payload(response.json())
        return contact_inbox.get("source_id") or generated_source_id

    def _notify(self, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Chatwoot",
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

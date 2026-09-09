import logging
import urllib.parse

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

DEFAULT_SUB_SUPPLIER_API_URL = (
    "https://ncc-api.hanoicheck.com.vn/supplier/sub-suppliers/paginate"
    "?page=1&per_page=15"
)


class ResPartner(models.Model):
    _inherit = "res.partner"

    crall_sub_supplier_id = fields.Char(
        string="Sub-supplier ID", index=True, copy=False
    )
    crall_sub_supplier_code = fields.Char(string="Sub-supplier code", copy=False)
    crall_parent_supplier_id = fields.Char(
        string="Parent supplier ID", index=True, copy=False
    )
    crall_sub_supplier_food_category_ids = fields.Json(
        string="Sub-supplier food categories", copy=False
    )
    crall_sub_supplier_certificates = fields.Json(
        string="Sub-supplier certificates", copy=False
    )
    crall_sub_supplier_contracts = fields.Json(
        string="Sub-supplier contracts", copy=False
    )
    crall_sub_supplier_payload = fields.Json(string="Sub-supplier payload", copy=False)

    def sync_crall_sub_suppliers(self, url=None, token=None, referer=None, page=1):
        parameters = self.env["ir.config_parameter"].sudo()
        url = url or parameters.get_param(
            "crall_material.sub_supplier_api_url",
            DEFAULT_SUB_SUPPLIER_API_URL,
        )
        token = token or parameters.get_param("crall_material.supplier_api_token")
        referer = referer or parameters.get_param(
            "crall_material.supplier_api_referer",
            "https://ncc.hanoicheck.com.vn",
        )
        if not token:
            raise UserError(_("Chưa cấu hình token API của nhà cung cấp."))
        if not token.lower().startswith("bearer "):
            token = "Bearer %s" % token

        url = self._crall_paginated_url((url or "").strip(), page)

        try:
            response = requests.get(
                url,
                headers={
                    "Authorization": token,
                    "Referer": referer,
                    "Accept": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as error:
            _logger.exception("Could not fetch Crall sub-suppliers")
            raise UserError(
                _("Không thể lấy dữ liệu nhà cung cấp phụ: %s") % error
            ) from error

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "json" not in content_type:
            _logger.warning(
                "Crall sub-supplier API returned non-JSON content (HTTP %s, Content-Type: %s)",
                response.status_code,
                content_type or "unknown",
            )
            raise UserError(
                _(
                    "API không trả về JSON (HTTP %s, Content-Type: %s). "
                    "URL có thể sai hoặc thiếu token hợp lệ."
                )
                % (response.status_code, content_type or _("không rõ"))
            )
        body_preview = (response.text or "")[:500]
        try:
            payload = response.json()
        except ValueError as error:
            _logger.warning(
                "Crall sub-supplier API returned non-JSON (HTTP %s): %s",
                response.status_code,
                body_preview,
            )
            raise UserError(
                _("API trả về dữ liệu không phải JSON (HTTP %s): %s")
                % (
                    response.status_code,
                    body_preview if body_preview.strip() else _("(body rỗng)"),
                )
            ) from error

        suppliers = self._crall_supplier_list(payload)
        if not suppliers:
            raise UserError(_("Không có dữ liệu ở trang %s.") % page)

        created = updated = skipped = 0
        for supplier in suppliers:
            if not isinstance(supplier, dict):
                continue
            supplier_id = self._crall_sub_value(
                supplier, "id", "supplier_id", "sub_supplier_id", "partner_id"
            )
            name = self._crall_sub_value(
                supplier,
                "name",
                "supplier_name",
                "sub_supplier_name",
                "company_name",
                "display_name",
                "title",
            )
            if supplier_id in (None, "", False) or not name:
                _logger.warning(
                    "Skipping sub-supplier without id or name: %s", supplier
                )
                skipped += 1
                continue

            supplier_id = str(supplier_id)
            supplier_code = self._crall_sub_value(
                supplier, "code", "supplier_code", "sub_supplier_code", "sku"
            )
            values = {
                "name": str(name),
                "is_company": True,
                "supplier_rank": 1,
                "ref": supplier_code if supplier_code else False,
                "vat": self._crall_sub_value(
                    supplier, "tax_number", "tax_code", "tax_id", "tax", "mst", "vat"
                )
                or False,
                "street": self._crall_sub_address(supplier) or False,
                "email": self._crall_sub_value(supplier, "email") or False,
                "phone": self._crall_sub_value(supplier, "phone", "phone_number")
                or False,
                "crall_sub_supplier_id": supplier_id,
                "crall_sub_supplier_code": supplier_code,
                "crall_parent_supplier_id": self._crall_sub_value(
                    supplier, "supplier_id", "parent_id", "parent_supplier_id"
                )
                or False,
                "crall_sub_supplier_food_category_ids": self._crall_sub_value(
                    supplier, "food_category_ids", "category_ids"
                )
                or False,
                "crall_sub_supplier_certificates": self._crall_sub_value(
                    supplier, "certificates", "certs", "certificate_list"
                )
                or False,
                "crall_sub_supplier_contracts": self._crall_sub_value(
                    supplier, "contracts", "contract_list"
                )
                or False,
                "crall_sub_supplier_payload": supplier,
            }
            vat = values.get("vat")
            domain = [("crall_sub_supplier_id", "=", supplier_id)]
            if vat:
                domain = [
                    "|",
                    ("crall_sub_supplier_id", "=", supplier_id),
                    ("vat", "=", vat),
                ]
            partner = self.search(domain, limit=1)
            if partner:
                partner.write(values)
                _logger.info(
                    "Updated Crall sub-supplier id=%s code=%s vat=%s",
                    supplier_id,
                    supplier_code,
                    vat,
                )
                updated += 1
                continue

            self.create(values)
            _logger.info(
                "Created Crall sub-supplier id=%s code=%s vat=%s",
                supplier_id,
                supplier_code,
                vat,
            )
            created += 1

        _logger.info(
            "Crall sub-suppliers synchronized: page %s, "
            "%s created, %s updated, %s skipped",
            page,
            created,
            updated,
            skipped,
        )
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "page": page,
        }

    def action_sync_crall_sub_suppliers_list(self):
        try:
            result = self.env["res.partner"].sync_crall_sub_suppliers()
        except UserError as error:
            raise UserError(
                _(
                    "%s Vui lòng cấu hình token ở Cài đặt > Crall Materials "
                    "hoặc dùng menu Craw Materials."
                )
                % error
            ) from error
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": "Sub-suppliers: %s created, %s updated, %s skipped"
                % (result["created"], result["updated"], result["skipped"]),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    @staticmethod
    def _crall_paginated_url(url, page):
        parts = urllib.parse.urlsplit(url)
        query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(
                parts.query, keep_blank_values=True
            )
            if key != "page"
        ]
        query.append(("page", str(page)))
        return urllib.parse.urlunsplit(
            parts._replace(query=urllib.parse.urlencode(query))
        )

    @staticmethod
    def _crall_sub_value(supplier, *keys):
        for key in keys:
            value = supplier.get(key)
            if value not in (None, ""):
                return value
        return False

    @staticmethod
    def _crall_sub_address(supplier):
        address = ResPartner._crall_sub_value(
            supplier, "address", "full_address", "address_line", "street"
        )
        if isinstance(address, dict):
            parts = [
                address.get(key)
                for key in (
                    "street",
                    "address_line",
                    "ward",
                    "district",
                    "city",
                    "province",
                    "zip",
                    "country",
                )
            ]
            return ", ".join(str(part) for part in parts if part not in (None, ""))
        if address not in (None, "", False):
            return address
        return False

    @staticmethod
    def _crall_supplier_list(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("data", "items", "results", "suppliers", "sub_suppliers"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = ResPartner._crall_supplier_list(value)
                if nested:
                    return nested
        return []

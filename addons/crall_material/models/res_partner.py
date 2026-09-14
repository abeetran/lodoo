import logging
import urllib.parse

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

from .hnck_client import HnckClient


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
    school_code = fields.Char(
        string="School ID", index=True, copy=False
    )
    school_payload = fields.Json(string="School payload", copy=False)
    school_year = fields.Char(string="Năm học", copy=False)
    certificate_ids = fields.One2many(
        "crall.supplier.certificate", "partner_id", string="Giấy chứng nhận ATTP"
    )
    contract_ids = fields.One2many(
        "crall.supplier.contract", "partner_id", string="Hợp đồng"
    )

    def _crall_resolve_api(self, url=None, token=None, referer=None):
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
        return url, token, referer

    def _fetch_crall_suppliers_page(self, url, token, referer, page):
        request_url = self._crall_paginated_url((url or "").strip(), page)
        try:
            response = requests.get(
                request_url,
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

        return request_url, self._crall_supplier_list(payload)

    def fetch_all_crall_sub_suppliers(
        self, url=None, token=None, referer=None, max_pages=200
    ):
        url, token, referer = self._crall_resolve_api(url, token, referer)
        suppliers, page = [], 1
        while page <= max_pages:
            _request_url, page_suppliers = self._fetch_crall_suppliers_page(
                url, token, referer, page
            )
            if not page_suppliers:
                break
            suppliers.extend(page_suppliers)
            page += 1
        return suppliers

    def sync_crall_sub_suppliers(self, url=None, token=None, referer=None, page=1):
        url, token, referer = self._crall_resolve_api(url, token, referer)
        _request_url, suppliers = self._fetch_crall_suppliers_page(
            url, token, referer, page
        )
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

    def action_create_supplier_contract(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Hợp đồng mới"),
            "res_model": "crall.supplier.contract",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }

    def sync_crall_schools(
        self, url=None, token=None, referer=None, max_pages=200, page=None, per_page=None
    ):
        parameters = self.env["ir.config_parameter"].sudo()
        url = url or parameters.get_param(
            "crall_material.school_api_url",
            "https://ncc-api.hanoicheck.com.vn/supplier/schools/paginate?page=1&per_page=30",
        )
        if per_page:
            url = self._crall_page_size_url(url, per_page)
        token = token or parameters.get_param("crall_material.supplier_api_token")
        referer = referer or parameters.get_param(
            "crall_material.supplier_api_referer",
            "https://ncc.hanoicheck.com.vn",
        )
        if not token:
            raise UserError(_("Chưa cấu hình token API của nhà cung cấp."))
        if not token.lower().startswith("bearer "):
            token = "Bearer %s" % token

        created = updated = skipped = 0
        single_page = page is not None
        page = page or 1
        while page <= max_pages:
            _request_url, schools = self._fetch_crall_suppliers_page(
                url, token, referer, page
            )
            if not schools:
                break
            for school in schools:
                if not isinstance(school, dict):
                    skipped += 1
                    continue
                school_id = self._crall_sub_value(school, "id", "school_id")
                name = self._crall_sub_value(
                    school, "name", "school_name", "display_name", "title"
                )
                if school_id in (None, "", False) or not name:
                    _logger.warning(
                        "Skipping school without id or name: %s", school
                    )
                    skipped += 1
                    continue
                school_id = str(school_id)
                school_code = self._crall_sub_value(
                    school, "code", "school_code", "sku"
                )
                values = {
                    "name": str(name),
                    "is_company": True,
                    "customer_rank": 1,
                    "ref": school_code if school_code else False,
                    "street": self._crall_sub_address(school) or False,
                    "school_code": school_id,
                    "school_year": self._crall_latest_school_year(school)
                    or False,
                    "school_payload": school,
                }
                partner = self.search(
                    [("school_code", "=", school_id)], limit=1
                )
                if partner:
                    partner.write(values)
                    updated += 1
                    continue
                self.create(values)
                created += 1
            if single_page:
                break
            page += 1

        _logger.info(
            "Crall schools synchronized: %s created, %s updated, %s skipped",
            created,
            updated,
            skipped,
        )
        return {"created": created, "updated": updated, "skipped": skipped}

    def action_sync_crall_schools_list(self):
        result = self.env["res.partner"].sync_crall_schools()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": "Trường học: %s created, %s updated, %s skipped"
                % (result["created"], result["updated"], result["skipped"]),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def action_sync_crall_sub_suppliers_list(self):
        if not self:
            raise UserError(_("Vui lòng chọn ít nhất một nhà cung cấp."))
        records = [
            {
                "ma_co_so": partner.ref
                or partner.crall_sub_supplier_code
                or "",
                "ten_co_so": partner.name or "",
                "dia_chi": partner.street or "",
            }
            for partner in self
        ]
        result = HnckClient(self.env).merge_facilities(records)
        message = _("Đã đẩy %s nhà cung cấp lên HNCK.") % len(records)
        if isinstance(result, dict) and result.get("message"):
            message = "%s %s" % (message, result["message"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    @staticmethod
    def _crall_latest_school_year(school):
        years = (school or {}).get("school_years") or []
        if isinstance(years, str):
            years = [years]
        candidates = [
            year for year in years if year not in (None, "")
        ]
        if not candidates:
            single = (school or {}).get("school_year")
            return single if single not in (None, "") else False
        def _year_key(year):
            digits = "".join(
                char for char in str(year)[:4] if char.isdigit()
            )
            return (int(digits) if len(digits) == 4 else 0, str(year))

        return max(candidates, key=_year_key)

    @staticmethod
    def _crall_page_size_url(url, per_page):
        parts = urllib.parse.urlsplit((url or "").strip())
        query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(
                parts.query, keep_blank_values=True
            )
            if key != "per_page"
        ]
        query.append(("per_page", str(per_page)))
        return urllib.parse.urlunsplit(
            parts._replace(query=urllib.parse.urlencode(query))
        )

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

import logging

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    crall_supplier_id = fields.Char(string="Supplier food ID", index=True, copy=False)
    crall_supplier_code = fields.Char(string="Supplier food code", copy=False)
    crall_measure_id = fields.Integer(string="Supplier measure ID", copy=False)
    crall_measure_name = fields.Char(string="Supplier measure", copy=False)
    crall_game_exchange = fields.Float(string="Gram exchange", copy=False)
    crall_is_meat = fields.Boolean(string="Is meat", copy=False)
    crall_is_dry = fields.Boolean(string="Is dry", copy=False)
    crall_supplier_payload = fields.Json(string="Supplier payload", copy=False)

    def sync_crall_materials(self, url=None, token=None, referer=None):
        parameters = self.env["ir.config_parameter"].sudo()
        url = url or parameters.get_param(
            "crall_material.supplier_api_url",
            "https://ncc-api.hanoicheck.com.vn/supplier/standard-foods",
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
            payload = response.json()
        except requests.exceptions.RequestException as error:
            _logger.exception("Could not fetch Crall supplier foods")
            raise UserError(_("Không thể lấy dữ liệu nguyên liệu: %s") % error) from error
        except ValueError as error:
            raise UserError(_("API trả về dữ liệu JSON không hợp lệ.")) from error

        foods = self._crall_food_list(payload)
        if not foods:
            raise UserError(_("API không trả về danh sách nguyên liệu."))

        created = updated = 0
        for food in foods:
            if not isinstance(food, dict):
                continue
            supplier_id = self._crall_value(food, "id", "food_id", "product_id")
            name = self._crall_value(
                food, "name", "food_name", "product_name", "title", "standard_food_name"
            )
            if supplier_id in (None, "") or not name:
                _logger.warning("Skipping supplier food without id or name: %s", food)
                continue

            supplier_id = str(supplier_id)
            supplier_code = self._crall_value(
                food, "code", "food_code", "product_code", "sku"
            )
            measure_name = self._crall_value(food, "measure_name", "uom_name")
            values = {
                "name": str(name),
                "default_code": supplier_code,
                "crall_supplier_id": supplier_id,
                "crall_supplier_code": supplier_code,
                "crall_measure_id": self._crall_value(food, "measure_id", "uom_id"),
                "crall_measure_name": measure_name,
                "crall_game_exchange": self._crall_value(
                    food, "game_exchange", "gam_exchange"
                ),
                "crall_is_meat": bool(food.get("is_meat", False)),
                "crall_is_dry": bool(food.get("is_dry", False)),
                "crall_supplier_payload": food,
            }
            if measure_name:
                uom = self.env["uom.uom"].search(
                    [("name", "=", str(measure_name))], limit=1
                )
                if uom:
                    values["uom_id"] = uom.id
            domain = [("crall_supplier_id", "=", supplier_id)]
            if supplier_code:
                domain = [
                    "|",
                    ("crall_supplier_id", "=", supplier_id),
                    ("crall_supplier_code", "=", str(supplier_code)),
                ]
            product = self.search(domain, limit=1)
            if product:
                _logger.info(
                    "Skipping existing Crall material id=%s code=%s",
                    supplier_id,
                    supplier_code,
                )
            else:
                self.create(values)
                created += 1

        _logger.info("Crall materials synchronized: %s created, %s updated", created, updated)
        return {"created": created, "updated": updated}

    @staticmethod
    def _crall_value(food, *keys):
        for key in keys:
            value = food.get(key)
            if value not in (None, ""):
                return value
        return False

    @staticmethod
    def _crall_food_list(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("data", "items", "results", "foods", "products"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = ProductTemplate._crall_food_list(value)
                if nested:
                    return nested
        return []
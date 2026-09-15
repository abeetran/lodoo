import logging
import urllib.parse

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

DEFAULT_FOOD_API_URL = (
    "https://ncc-api.hanoicheck.com.vn/supplier/foods/paginate"
    "?page=1&page_size=15"
)


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
    crall_food_source = fields.Selection(
        [("standard", "Thực phẩm chuẩn"), ("foods", "Thực phẩm")],
        string="Nguồn thực phẩm",
        copy=False,
        index=True,
    )

    def sync_crall_materials(self, url=None, token=None, referer=None, page=1):
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

        page_size = 100
        page_start = (page - 1) * page_size
        page_foods = foods[page_start : page_start + page_size]
        if not page_foods:
            raise UserError(_("Không có dữ liệu ở trang %s.") % page)

        counts = self._crall_upsert_foods(page_foods, source="standard")
        created = counts["created"]
        updated = counts["updated"]
        skipped = counts["skipped"]

        _logger.info(
            "Crall materials synchronized: page %s, %s created, %s updated, %s skipped",
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
            "product_ids": counts["product_ids"],
        }

    def sync_crall_foods(
        self, url=None, token=None, referer=None, page=1, page_size=15
    ):
        """Fetch one page from ``supplier/foods/paginate`` into products.

        ``page``/``token`` come from the Data Sync wizard; ``page_size``
        defaults to 15 like the API example. Saved records carry source
        ``foods`` so they show up in the Materials menu, not in
        ``Danh mục thực phẩm chuẩn``.
        """
        parameters = self.env["ir.config_parameter"].sudo()
        url = url or parameters.get_param(
            "crall_material.food_api_url",
            DEFAULT_FOOD_API_URL,
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

        _request_url, foods = self._fetch_crall_foods_page(
            url, token, referer, page, page_size
        )
        if not foods:
            raise UserError(_("Không có dữ liệu ở trang %s.") % page)

        counts = self._crall_upsert_foods(foods, source="foods")
        created = counts["created"]
        updated = counts["updated"]
        skipped = counts["skipped"]
        _logger.info(
            "Crall foods synchronized: page %s (page_size %s), "
            "%s created, %s updated, %s skipped",
            page,
            page_size,
            created,
            updated,
            skipped,
        )
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "page": page,
            "page_size": page_size,
            "product_ids": counts["product_ids"],
        }

    def sync_crall_foods_all(
        self, url=None, token=None, referer=None, page_size=15, max_pages=200
    ):
        """Fetch every foods/paginate page until an empty page is reached.

        Accumulates created/updated/skipped over all visited pages so items
        living beyond page 1 (e.g. searched foods) are also imported.
        """
        parameters = self.env["ir.config_parameter"].sudo()
        url = url or parameters.get_param(
            "crall_material.food_api_url",
            DEFAULT_FOOD_API_URL,
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

        created = updated = skipped = pages = 0
        product_ids = []
        page = 1
        while page <= max_pages:
            _request_url, foods = self._fetch_crall_foods_page(
                url, token, referer, page, page_size
            )
            if not foods:
                break
            counts = self._crall_upsert_foods(foods, source="foods")
            created += counts["created"]
            updated += counts["updated"]
            skipped += counts["skipped"]
            product_ids.extend(counts["product_ids"])
            pages += 1
            page += 1
        if not pages:
            raise UserError(_("API không trả về danh sách thực phẩm."))
        _logger.info(
            "Crall foods synchronized: %s pages (page_size %s), "
            "%s created, %s updated, %s skipped",
            pages,
            page_size,
            created,
            updated,
            skipped,
        )
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "pages": pages,
            "page_size": page_size,
            "product_ids": product_ids,
        }

    def _fetch_crall_foods_page(self, url, token, referer, page, page_size):
        request_url = self._crall_foods_page_url(url, page, page_size)
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
            payload = response.json()
        except requests.exceptions.RequestException as error:
            _logger.exception("Could not fetch Crall supplier foods page")
            raise UserError(_("Không thể lấy dữ liệu thực phẩm: %s") % error) from error
        except ValueError as error:
            raise UserError(_("API trả về dữ liệu JSON không hợp lệ.")) from error
        return request_url, self._crall_food_list(payload)

    def _crall_upsert_foods(self, foods, source="standard"):
        created = updated = skipped = 0
        product_ids = []
        for food in foods:
            if not isinstance(food, dict):
                skipped += 1
                continue
            supplier_id = self._crall_value(
                food,
                "id",
                "food_id",
                "standard_food_id",
                "foodId",
                "foodID",
                "product_id",
            )
            name = self._crall_value(
                food,
                "name",
                "food_name",
                "product_name",
                "title",
                "standard_food_name",
                "foodName",
            )
            if supplier_id in (None, "", False) or not name:
                _logger.warning("Skipping supplier food without id or name: %s", food)
                skipped += 1
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
                "crall_food_source": source,
            }
            if measure_name:
                uom = self.env["uom.uom"].search(
                    [("name", "=", str(measure_name))], limit=1
                )
                if uom:
                    values["uom_id"] = uom.id
            # Đã tồn tại (khớp đúng supplier ID) -> cập nhật;
            # chưa có mới khớp theo mã rồi nhận về, còn lại thì thêm mới.
            product = self.search(
                [("crall_supplier_id", "=", supplier_id)], limit=1
            )
            if not product and supplier_code:
                product = self.search(
                    [
                        "|",
                        ("crall_supplier_code", "=", str(supplier_code)),
                        ("default_code", "=", str(supplier_code)),
                    ],
                    limit=1,
                )
            if product:
                update_vals = dict(values)
                if not supplier_code:
                    update_vals.pop("default_code", None)
                product.write(update_vals)
                _logger.info(
                    "Updated Crall material id=%s code=%s",
                    supplier_id,
                    supplier_code,
                )
                product_ids.append(product.id)
                updated += 1
                continue

            new_product = self.create(values)
            product_ids.append(new_product.id)
            created += 1

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "product_ids": product_ids,
        }

    @staticmethod
    def _crall_foods_page_url(url, page, page_size):
        parts = urllib.parse.urlsplit((url or "").strip())
        query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(
                parts.query, keep_blank_values=True
            )
            if key not in ("page", "page_size")
        ]
        query.append(("page", str(page)))
        query.append(("page_size", str(page_size)))
        return urllib.parse.urlunsplit(
            parts._replace(query=urllib.parse.urlencode(query))
        )

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
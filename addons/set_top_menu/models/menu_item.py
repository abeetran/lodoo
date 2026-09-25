import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext

from odoo.addons.crall_material.models.hnck_client import HnckClient


_logger = logging.getLogger(__name__)


def serialize_supplier_dish(
    item_code,
    name,
    description_text,
    age_group_id,
    procedure_code,
    ingredients,
    khau_list,
):
    """Build the POST body dict for ``supplier/dishes/merge`` from plain values.

    Pure function (no record access) so the body format stays testable.
    """
    return {
        "ma_mon_an": item_code or "",
        "ten_mon_an": name or "",
        "nhom_tuoi_id": age_group_id or False,
        "mo_ta": description_text or "",
        "ma_quy_trinh": procedure_code or "",
        "danh_sach_nguyen_lieu": ingredients or [],
        "danh_sach_khau": khau_list or [],
    }


class MenuItem(models.Model):
    _name = "set_top_menu.menu.item"
    _description = "Món ăn"
    _order = "name"

    name = fields.Char(string="Tên món", required=True, index=True)
    item_code = fields.Char(string="Mã món", required=True, copy=False, index=True)
    process_id = fields.Many2one(
        "set_top_menu.production.process",
        string="Quy trình sản xuất",
        ondelete="restrict",
        help="Quy trình sản xuất món ăn này (lấy từ danh sách QL Quy trình SX).",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Thành phẩm",
        readonly=True,
        help="Thành phẩm được lấy tự động từ công thức sản xuất.",
    )
    image_1920 = fields.Image(string="Ảnh món ăn", max_width=1920, max_height=1920)
    food_category = fields.Selection(
        [
            ("vegetarian", "Món chay"),
            ("non_vegetarian", "Món mặn"),
            ("vegan", "Thuần chay"),
            ("egg", "Món trứng"),
        ],
        string="Loại thực phẩm",
        required=True,
        default="vegetarian",
    )
    serving_size = fields.Float(string="Khẩu phần tiêu chuẩn", required=True, default=1.0)
    serving_uom_id = fields.Many2one("uom.uom", string="Đơn vị khẩu phần", required=True)
    cost_per_serving = fields.Monetary(
        string="Chi phí mỗi khẩu phần",
        currency_field="currency_id",
        compute="_compute_cost_per_serving",
        store=True,
    )
    sale_price = fields.Monetary(
        string="Giá bán mỗi suất", currency_field="currency_id", default=0.0
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    active = fields.Boolean(string="Đang hoạt động", default=True)
    meal_type_ids = fields.Many2many(
        "set_top_menu.meal.type", string="Bữa ăn áp dụng"
    )
    dietary_tag_ids = fields.Many2many(
        "set_top_menu.dietary.tag", string="Nhãn chế độ ăn"
    )
    allergen_ids = fields.Many2many("set_top_menu.allergen", string="Chất gây dị ứng")
    age_group_id = fields.Many2one(
        "set_top_menu.age.group", string="Nhóm tuổi"
    )
    ingredient_ids = fields.One2many(
        "set_top_menu.menu.ingredient", "menu_item_id", string="Nguyên liệu công thức", copy=True
    )
    description = fields.Html(string="Mô tả")
    production_site_ids = fields.Many2many(
        "crall.production.site", string="Cơ sở sản xuất"
    )
    supplier_procedure_code = fields.Char(
        string="Mã quy trình NCC", copy=False, index=True,
        help="ma_quy_trinh nhận từ API nhà cung cấp.",
    )
    supplier_age_group_id = fields.Integer(
        string="Nhóm tuổi NCC", copy=False,
        help="nhom_tuoi_id nhận từ API nhà cung cấp.",
    )
    supplier_payload = fields.Json(
        string="Dữ liệu NCC", copy=False, readonly=True,
        help="Toàn bộ thông tin món ăn nhận từ API (nguyên liệu, công đoạn, người thực hiện, files).",
    )

    _sql_constraints = [
        ("item_code_unique", "unique(item_code)", "Mã món không được trùng."),
        ("product_unique", "unique(product_id)", "Sản phẩm bán hàng đã được liên kết với món khác."),
    ]

    @api.depends("ingredient_ids.cost")
    def _compute_cost_per_serving(self):
        for item in self:
            item.cost_per_serving = sum(item.ingredient_ids.mapped("cost"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("product_id"):
                product = self.env["product.product"].create(
                    {
                        "name": vals.get("name") or "Menu Item",
                        "default_code": vals.get("item_code"),
                        "sale_ok": True,
                        "purchase_ok": False,
                        "list_price": vals.get("sale_price", 0.0),
                    }
                )
                vals["product_id"] = product.id
        return super().create(vals_list)

    def _ensure_sale_product(self):
        for item in self.filtered(lambda record: not record.product_id):
            product = self.env["product.product"].create(
                {
                    "name": item.name,
                    "default_code": item.item_code,
                    "sale_ok": True,
                    "purchase_ok": False,
                    "list_price": item.sale_price,
                }
            )
            item.product_id = product
        return self.mapped("product_id")

    def write(self, vals):
        result = super().write(vals)
        if "sale_price" in vals:
            self.mapped("product_id").write({"list_price": vals["sale_price"]})
        return result

    def action_push_supplier_dishes(self):
        """Nút Đồng bộ: chỉ hiện khi tick chọn món ăn trên danh sách.

        Gửi các món đang chọn lên API ``supplier/dishes/merge`` (POST).
        """
        if not self:
            raise UserError(_("Vui lòng chọn ít nhất một món ăn để đồng bộ."))
        payloads = [dish._supplier_dish_payload() for dish in self]
        result = HnckClient(self.env).push_supplier_dishes(payloads)
        message = _("Đã gửi %s món ăn lên API nhà cung cấp.") % len(payloads)
        if isinstance(result, dict) and result.get("message"):
            message = "%s %s" % (message, result["message"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đồng bộ món ăn"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def _supplier_dish_payload(self):
        """Serialize one dish into the supplier merge body format."""
        self.ensure_one()
        stored = (
            self.supplier_payload
            if isinstance(self.supplier_payload, dict)
            else {}
        )
        description_text = (
            html2plaintext(self.description or "").strip()
            if self.description
            else ""
        )
        if not description_text:
            description_text = stored.get("mo_ta") or ""
        ingredients = (
            self._supplier_push_ingredients()
            or stored.get("danh_sach_nguyen_lieu")
            or []
        )
        return serialize_supplier_dish(
            self.item_code,
            self.name,
            description_text,
            self.supplier_age_group_id,
            self.supplier_procedure_code,
            ingredients,
            stored.get("danh_sach_khau") or [],
        )

    def _supplier_push_ingredients(self):
        """Map ingredient lines to ``danh_sach_nguyen_lieu`` entries."""
        lines = []
        for line in self.ingredient_ids:
            template = line.product_id.product_tmpl_id
            code = (
                template.crall_supplier_code
                or template.default_code
                or line.product_id.barcode
                or ""
            )
            if not code or (line.quantity or 0) <= 0:
                _logger.warning(
                    "Skipping dish ingredient without code or quantity: %s",
                    line.display_name,
                )
                continue
            lines.append(
                {
                    "ma_nguyen_lieu": code,
                    "dinh_luong": line.quantity,
                    "don_vi_tinh_id": line.uom_id.id,
                }
            )
        return lines

    def action_sync_supplier_dishes(self):
        """Nút Sync trên màn hình danh sách món ăn.

        Chạy được cả khi không chọn dòng nào: lấy danh sách món ăn từ
        API ``supplier/dishes/merge`` (tự kiểm tra/refresh token), món đã
        tồn tại theo ``ma_mon_an`` thì cập nhật, chưa có thì tạo mới.
        """
        result = self.sync_supplier_dishes()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đồng bộ món ăn"),
                "message": _(
                    "%s mới, %s cập nhật, %s bỏ qua."
                )
                % (result["created"], result["updated"], result["skipped"]),
                "type": "success"
                if result["created"] or result["updated"]
                else "warning",
                "sticky": False,
            },
        }

    @api.model
    def sync_supplier_dishes(self, url=None):
        dishes = HnckClient(self.env).fetch_supplier_dishes(url=url)
        if not dishes:
            raise UserError(_("API không trả về danh sách món ăn."))
        created = updated = skipped = 0
        for dish in dishes:
            if not isinstance(dish, dict):
                skipped += 1
                continue
            dish_code = dish.get("ma_mon_an")
            if dish_code in (None, ""):
                _logger.warning("Skipping supplier dish without ma_mon_an: %s", dish)
                skipped += 1
                continue
            dish_code = str(dish_code)
            ingredient_commands = self._supplier_ingredient_commands(
                dish.get("danh_sach_nguyen_lieu") or []
            )
            values = {
                "name": str(dish.get("ten_mon_an") or dish_code),
                "description": "<p>%s</p>" % dish.get("mo_ta")
                if dish.get("mo_ta")
                else False,
                "supplier_procedure_code": str(dish.get("ma_quy_trinh") or False)
                if dish.get("ma_quy_trinh")
                else False,
                "supplier_age_group_id": dish.get("nhom_tuoi_id") or False,
                "supplier_payload": dish,
            }
            existing = self.search([("item_code", "=", dish_code)], limit=1)
            if existing:
                if ingredient_commands:
                    values["ingredient_ids"] = ingredient_commands
                existing.write(values)
                updated += 1
                continue
            create_vals = dict(values, item_code=dish_code)
            create_vals.setdefault("serving_size", 1.0)
            create_vals["serving_uom_id"] = self._default_supplier_serving_uom(
                ingredient_commands
            )
            if ingredient_commands:
                create_vals["ingredient_ids"] = ingredient_commands
            self.create(create_vals)
            created += 1
        _logger.info(
            "Supplier dishes synchronized: %s created, %s updated, %s skipped",
            created,
            updated,
            skipped,
        )
        return {"created": created, "updated": updated, "skipped": skipped}

    def _supplier_ingredient_commands(self, ingredients):
        """Build ingredient line commands from ``danh_sach_nguyen_lieu``.

        Mỗi dòng gồm ``ma_nguyen_lieu`` (khớp sản phẩm theo mã),
        ``dinh_luong`` (số lượng) và ``don_vi_tinh_id`` (đơn vị tính).
        Dòng không khớp được sản phẩm hoặc số lượng <= 0 sẽ bị bỏ qua.
        """
        commands = [Command.clear()]
        lines = 0
        for ingredient in ingredients if isinstance(ingredients, list) else []:
            if not isinstance(ingredient, dict):
                continue
            material_code = ingredient.get("ma_nguyen_lieu")
            if material_code in (None, ""):
                continue
            try:
                quantity = float(ingredient.get("dinh_luong") or 0)
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue
            product = self._resolve_supplier_product(str(material_code))
            if not product:
                _logger.warning(
                    "Skipping dish ingredient without matching product: %s",
                    material_code,
                )
                continue
            uom = product.uom_id
            supplier_uom_id = ingredient.get("don_vi_tinh_id")
            if supplier_uom_id:
                try:
                    candidate = self.env["uom.uom"].browse(int(supplier_uom_id))
                    if candidate.exists():
                        uom = candidate
                except (TypeError, ValueError):
                    pass
            commands.append(
                Command.create(
                    {
                        "product_id": product.id,
                        "quantity": quantity,
                        "uom_id": uom.id,
                        "unit_cost": product.standard_price,
                    }
                )
            )
            lines += 1
        return commands if lines else []

    def _resolve_supplier_product(self, code):
        template = self.env["product.template"].search(
            [("default_code", "=", code)], limit=1
        )
        if not template:
            template = self.env["product.template"].search(
                [("crall_supplier_code", "=", code)], limit=1
            )
        if not template:
            template = self.env["product.template"].search(
                [("crall_supplier_id", "=", code)], limit=1
            )
        return template.product_variant_id if template else False

    def _default_supplier_serving_uom(self, ingredient_commands):
        for command in ingredient_commands or []:
            if command[0] == 0 and command[2].get("uom_id"):
                return command[2]["uom_id"]
        unit = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        if unit:
            return unit.id
        fallback = self.env["uom.uom"].search([], limit=1)
        if not fallback:
            raise UserError(
                _("Không tìm thấy đơn vị tính nào để tạo món ăn mới.")
            )
        return fallback.id

class MenuIngredient(models.Model):
    _name = "set_top_menu.menu.ingredient"
    _description = "Nguyên liệu công thức"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    menu_item_id = fields.Many2one(
        "set_top_menu.menu.item", required=True, ondelete="cascade", index=True
    )
    product_id = fields.Many2one(
        "product.product", string="Nguyên liệu", required=True, domain="[('purchase_ok', '=', True)]"
    )
    quantity = fields.Float(string="Số lượng mỗi khẩu phần", required=True, default=1.0)
    uom_id = fields.Many2one("uom.uom", string="Đơn vị tính", required=True)
    unit_cost = fields.Float(string="Đơn giá", digits="Product Price")
    cost = fields.Monetary(
        string="Chi phí", currency_field="currency_id", compute="_compute_cost", store=True
    )
    currency_id = fields.Many2one(related="menu_item_id.currency_id", store=True)
    notes = fields.Char(string="Ghi chú")

    @api.depends("quantity", "unit_cost")
    def _compute_cost(self):
        for line in self:
            line.cost = line.quantity * line.unit_cost

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Số lượng nguyên liệu phải lớn hơn 0.")


class MealType(models.Model):
    _name = "set_top_menu.meal.type"
    _description = "Loại bữa ăn"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer()

    _sql_constraints = [("name_unique", "unique(name)", "Loại bữa ăn đã tồn tại.")]


class DietaryTag(models.Model):
    _name = "set_top_menu.dietary.tag"
    _description = "Nhãn chế độ ăn"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer()

    _sql_constraints = [("name_unique", "unique(name)", "Nhãn chế độ ăn đã tồn tại.")]


class Allergen(models.Model):
    _name = "set_top_menu.allergen"
    _description = "Chất gây dị ứng"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer()

    _sql_constraints = [("name_unique", "unique(name)", "Chất gây dị ứng đã tồn tại.")]


class AgeGroup(models.Model):
    _name = "set_top_menu.age.group"
    _description = "Nhóm tuổi"
    _order = "supplier_age_id, id"

    name = fields.Char(required=True)
    color = fields.Integer()
    supplier_age_id = fields.Integer(
        string="ID nhóm tuổi NCC",
        index=True,
        copy=False,
        help="nhom_tuoi_id 1-10 từ API nhà cung cấp.",
    )

    _sql_constraints = [("name_unique", "unique(name)", "Nhóm tuổi đã tồn tại.")]

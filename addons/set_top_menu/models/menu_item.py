from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError


class MenuItem(models.Model):
    _name = "set_top_menu.menu.item"
    _description = "Món ăn"
    _order = "name"

    name = fields.Char(string="Tên món", required=True, index=True)
    item_code = fields.Char(string="Mã món", required=True, copy=False, index=True)
    bom_id = fields.Many2one(
        "mrp.bom",
        string="Công thức sản xuất",
        domain="[('type', '=', 'normal')]",
        ondelete="restrict",
        help="Định mức nguyên vật liệu dùng để sản xuất món ăn này.",
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
    ingredient_ids = fields.One2many(
        "set_top_menu.menu.ingredient", "menu_item_id", string="Nguyên liệu công thức", copy=True
    )
    description = fields.Html(string="Mô tả")

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
            if vals.get("bom_id"):
                bom = self.env["mrp.bom"].browse(vals["bom_id"])
                vals["product_id"] = (bom.product_id or bom.product_tmpl_id.product_variant_id).id
            elif not vals.get("product_id"):
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
        if vals.get("bom_id"):
            bom = self.env["mrp.bom"].browse(vals["bom_id"])
            vals = {
                **vals,
                "product_id": (bom.product_id or bom.product_tmpl_id.product_variant_id).id,
            }
        result = super().write(vals)
        if "sale_price" in vals:
            self.mapped("product_id").write({"list_price": vals["sale_price"]})
        return result

    @api.onchange("bom_id")
    def _onchange_bom_id(self):
        for item in self:
            if not item.bom_id:
                item.ingredient_ids = [Command.clear()]
                continue

            bom = item.bom_id
            item.product_id = bom.product_id or bom.product_tmpl_id.product_variant_id
            item.serving_size = bom.product_qty
            item.serving_uom_id = bom.product_uom_id
            item.ingredient_ids = item._bom_ingredient_commands()

    def _bom_ingredient_commands(self):
        self.ensure_one()
        return [Command.clear()] + [
            Command.create(
                {
                    "product_id": line.product_id.id,
                    "quantity": line.product_qty,
                    "uom_id": line.product_uom_id.id,
                    "unit_cost": line.product_id.standard_price,
                }
            )
            for line in self.bom_id.bom_line_ids
        ]

    def action_sync_from_bom(self):
        for item in self:
            if not item.bom_id:
                raise ValidationError("Vui lòng chọn Công thức sản xuất trước khi đồng bộ.")
            item.write(
                {
                    "serving_size": item.bom_id.product_qty,
                    "serving_uom_id": item.bom_id.product_uom_id.id,
                    "ingredient_ids": item._bom_ingredient_commands(),
                }
            )
        return True

    @api.constrains("bom_id", "product_id")
    def _check_manufacturing_link(self):
        for item in self:
            if item.bom_id and not item.product_id:
                raise ValidationError("Công thức sản xuất phải có thành phẩm hợp lệ.")


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

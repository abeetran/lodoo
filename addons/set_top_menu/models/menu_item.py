from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MenuItem(models.Model):
    _name = "set_top_menu.menu.item"
    _description = "Món ăn"
    _order = "name"

    name = fields.Char(string="Tên món", required=True, index=True)
    item_code = fields.Char(string="Mã món", required=True, copy=False, index=True)
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
    ]

    @api.depends("ingredient_ids.cost")
    def _compute_cost_per_serving(self):
        for item in self:
            item.cost_per_serving = sum(item.ingredient_ids.mapped("cost"))


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

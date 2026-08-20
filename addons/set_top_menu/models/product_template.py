from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    menu_item_ids = fields.One2many(
        "set_top_menu.menu.item",
        "product_id",
        string="Món ăn liên kết",
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_menu_item_product = fields.Boolean(
        string="Là sản phẩm món ăn",
        compute="_compute_is_menu_item_product",
        store=True,
        compute_sudo=True,
    )

    @api.depends("product_variant_ids.menu_item_ids")
    def _compute_is_menu_item_product(self):
        for template in self:
            template.is_menu_item_product = bool(
                template.product_variant_ids.menu_item_ids
            )

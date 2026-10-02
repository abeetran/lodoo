from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = "product.product"

    menu_item_ids = fields.One2many(
        "set_top_menu.menu.item",
        "product_id",
        string="Món ăn liên kết",
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    process_ids = fields.Many2many(
        "set_top_menu.production.process",
        relation="product_template_process_rel",
        column1="template_id",
        column2="process_id",
        string="Quy trình sản xuất",
    )

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

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(
            "set_top_menu_require_food_fields"
        ) and not self.env.context.get("set_top_menu_food_copy"):
            for vals in vals_list:
                self._check_food_create_required(vals)
        return super().create(vals_list)

    def copy(self, default=None):
        self = self.with_context(set_top_menu_food_copy=True)
        return super().copy(default=default)

    @api.model
    def _check_food_create_required(self, vals):
        """Bắt buộc đủ 4 trường khi thêm mới thực phẩm (material).

        Chỉ chạy khi tạo từ màn hình Thực phẩm (nhận biết qua context của
        action); tạo từ API sync, nhân bản, hay sửa bản ghi cũ đều bỏ qua.
        """
        source = vals.get("crall_food_source") or self.env.context.get(
            "default_crall_food_source"
        )
        if source != "foods":
            return
        missing = []
        if not vals.get("name"):
            missing.append(_("Tên"))
        if not vals.get("crall_standard_food_id"):
            missing.append(_("Danh mục thực phẩm chuẩn"))
        if not self._has_process_commands(vals.get("process_ids")):
            missing.append(_("Quy trình sản xuất"))
        if not vals.get("default_code"):
            missing.append(_("Mã tham chiếu nội bộ"))
        if missing:
            raise ValidationError(
                _("Vui lòng nhập: %s.") % ", ".join(missing)
            )

    @staticmethod
    def _has_process_commands(commands):
        for command in commands or []:
            if not isinstance(command, (list, tuple)) or not command:
                continue
            if command[0] == 6:
                if len(command) > 2 and command[2]:
                    return True
            elif command[0] in (0, 4):
                return True
        return False

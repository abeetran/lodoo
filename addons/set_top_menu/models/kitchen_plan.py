from datetime import datetime, time, timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


class KitchenProductionPlan(models.Model):
    _name = "set_top_menu.kitchen.plan"
    _description = "Kế hoạch sản xuất bếp"
    _order = "production_date desc, id desc"

    name = fields.Char(
        string="Mã kế hoạch", required=True, copy=False, readonly=True, default="Mới"
    )
    production_date = fields.Date(
        string="Ngày sản xuất", required=True, default=fields.Date.context_today, index=True
    )
    meal_type_id = fields.Many2one("set_top_menu.meal.type", string="Loại bữa ăn", required=True)
    company_id = fields.Many2one(
        "res.company", string="Công ty", required=True, default=lambda self: self.env.company
    )
    state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("confirmed", "Đã xác nhận"),
            ("progress", "Đang thực hiện"),
            ("done", "Hoàn tất"),
        ],
        string="Trạng thái",
        required=True,
        default="draft",
        tracking=False,
        index=True,
    )
    line_ids = fields.One2many(
        "set_top_menu.kitchen.plan.line", "plan_id", string="Chi tiết sản xuất", copy=True
    )
    order_ids = fields.Many2many(
        "sale.order",
        relation="set_top_menu_kitchen_plan_sale_order_rel",
        column1="plan_id",
        column2="order_id",
        string="Đơn hàng nguồn",
        copy=False,
    )
    order_count = fields.Integer(string="Số đơn hàng", compute="_compute_totals")
    total_items = fields.Integer(string="Tổng số món", compute="_compute_totals", store=True)
    total_servings = fields.Float(string="Tổng khẩu phần", compute="_compute_totals", store=True)
    progress = fields.Float(string="Tiến độ (%)", compute="_compute_totals", store=True)
    notes = fields.Text(string="Ghi chú")

    _sql_constraints = [
        ("name_unique", "unique(name)", "Mã kế hoạch đã tồn tại."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Mới") == "Mới":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "set_top_menu.kitchen.plan"
                ) or "Mới"
        return super().create(vals_list)

    @api.depends("line_ids", "line_ids.quantity", "line_ids.state", "order_ids")
    def _compute_totals(self):
        for plan in self:
            plan.total_items = len(plan.line_ids)
            plan.total_servings = sum(plan.line_ids.mapped("quantity"))
            plan.order_count = len(plan.order_ids)
            if plan.line_ids:
                completed = len(plan.line_ids.filtered(lambda line: line.state == "done"))
                plan.progress = completed * 100.0 / len(plan.line_ids)
            else:
                plan.progress = 0.0

    def action_confirm(self):
        for plan in self:
            if not plan.line_ids:
                raise UserError("Vui lòng thêm ít nhất một món vào kế hoạch sản xuất.")
            plan.state = "confirmed"

    def action_start(self):
        for plan in self:
            if not plan.line_ids:
                raise UserError("Vui lòng thêm ít nhất một món vào kế hoạch sản xuất.")
            plan.state = "progress"
            plan.order_ids.filtered(lambda order: order.catering_state == "confirmed").write(
                {"catering_state": "in_production"}
            )

    def action_done(self):
        for plan in self:
            if plan.line_ids.filtered(lambda line: line.state != "done"):
                raise UserError("Vẫn còn món chưa hoàn tất.")
            plan.state = "done"
            plan._sync_orders_ready()

    def action_reset_draft(self):
        self.write({"state": "draft"})
        self.mapped("line_ids").write({"state": "pending", "prepared_quantity": 0.0})
        self.mapped("order_ids").filtered(
            lambda order: order.catering_state in ("in_production", "ready")
        ).write({"catering_state": "confirmed"})

    def _sync_orders_ready(self):
        orders = self.mapped("order_ids")
        for order in orders:
            if order.kitchen_plan_ids and not order.kitchen_plan_ids.filtered(
                lambda plan: plan.state != "done"
            ):
                order.catering_state = "ready"

    def action_view_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_orders")
        action["domain"] = [("id", "in", self.order_ids.ids)]
        return action

    def action_generate_from_orders(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError("Chỉ có thể tạo chi tiết khi kế hoạch đang ở trạng thái Nháp.")

        day_start = datetime.combine(self.production_date, time.min)
        day_end = day_start + timedelta(days=1)
        orders = self.env["sale.order"].search(
            [
                ("state", "=", "sale"),
                ("date_order", ">=", fields.Datetime.to_string(day_start)),
                ("date_order", "<", fields.Datetime.to_string(day_end)),
                ("company_id", "=", self.company_id.id),
            ]
        )
        menu_items = self.env["set_top_menu.menu.item"].search(
            [("product_id", "in", orders.order_line.product_id.ids)]
        )
        item_by_product = {item.product_id.id: item for item in menu_items}
        quantities = {}
        for sale_line in orders.order_line.filtered(lambda line: not line.display_type):
            item = item_by_product.get(sale_line.product_id.id)
            if item:
                quantities[item] = quantities.get(item, 0.0) + sale_line.product_uom_qty

        if not quantities:
            raise UserError(
                "Không tìm thấy món ăn đã liên kết sản phẩm trong các đơn hàng của ngày sản xuất."
            )

        self.write(
            {
                "order_ids": [Command.set(orders.ids)],
                "line_ids": [Command.clear()]
                + [
                    Command.create({"menu_item_id": item.id, "quantity": quantity})
                    for item, quantity in quantities.items()
                ],
            }
        )
        return True


class KitchenProductionPlanLine(models.Model):
    _name = "set_top_menu.kitchen.plan.line"
    _description = "Chi tiết kế hoạch sản xuất bếp"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    plan_id = fields.Many2one(
        "set_top_menu.kitchen.plan", required=True, ondelete="cascade", index=True
    )
    meal_type_id = fields.Many2one(related="plan_id.meal_type_id", string="Loại bữa ăn", store=True)
    menu_item_id = fields.Many2one(
        "set_top_menu.menu.item", string="Món ăn", required=True, ondelete="restrict"
    )
    food_category = fields.Selection(
        related="menu_item_id.food_category", string="Loại thực phẩm", store=True
    )
    quantity = fields.Float(string="Số lượng cần làm", required=True, default=1.0)
    uom_id = fields.Many2one(
        related="menu_item_id.serving_uom_id", string="Đơn vị tính", store=True
    )
    prepared_quantity = fields.Float(string="Số lượng đã làm", default=0.0)
    state = fields.Selection(
        [("pending", "Chờ thực hiện"), ("progress", "Đang làm"), ("done", "Hoàn tất")],
        string="Trạng thái",
        required=True,
        default="pending",
    )

    @api.constrains("quantity", "prepared_quantity")
    def _check_quantities(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Số lượng cần làm phải lớn hơn 0.")
            if line.prepared_quantity < 0:
                raise ValidationError("Số lượng đã làm không được âm.")

    def action_start(self):
        self.write({"state": "progress"})
        self.mapped("plan_id").filtered(lambda plan: plan.state == "confirmed").write(
            {"state": "progress"}
        )
        self.mapped("plan_id.order_ids").filtered(
            lambda order: order.catering_state == "confirmed"
        ).write({"catering_state": "in_production"})

    def action_done(self):
        for line in self:
            line.write({"state": "done", "prepared_quantity": line.quantity})
            plan = line.plan_id
            if plan.line_ids and not plan.line_ids.filtered(lambda item: item.state != "done"):
                plan.state = "done"
                plan._sync_orders_ready()

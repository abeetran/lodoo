from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

from odoo.addons.crall_material.models.hnck_client import HnckClient


class SaleOrder(models.Model):
    _inherit = "sale.order"
    _rec_name = "catering_reference"

    catering_reference = fields.Char(
        string="Mã đơn phục vụ", required=True, readonly=True, copy=False, default="Mới"
    )
    catering_state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("confirmed", "Đã xác nhận"),
            ("in_production", "Đang sản xuất"),
            ("ready", "Sẵn sàng"),
            ("dispatched", "Đã xuất giao"),
            ("delivered", "Đã giao"),
            ("cancelled", "Đã hủy"),
        ],
        string="Trạng thái phục vụ",
        default="draft",
        required=True,
        copy=False,
        index=True,
    )
    contract_id = fields.Many2one(
        "set_top_menu.client.contract",
        string="Hợp đồng",
        domain="[('client_id', '=', partner_id), ('status', '=', 'active'), "
        "('date_start', '<=', context_today()), "
        "('date_end', '>=', context_today())]",
        ondelete="restrict",
    )
    total_meals = fields.Float(string="Tổng số suất ăn", compute="_compute_total_meals", store=True)
    kitchen_plan_ids = fields.Many2many(
        "set_top_menu.kitchen.plan",
        relation="set_top_menu_kitchen_plan_sale_order_rel",
        column1="order_id",
        column2="plan_id",
        string="Kế hoạch bếp",
        copy=False,
    )
    kitchen_plan_count = fields.Integer(compute="_compute_kitchen_plan_count")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("catering_reference", "Mới") == "Mới":
                reference = self.env["ir.sequence"].next_by_code(
                    "set_top_menu.sale.order"
                ) or "Mới"
                vals["catering_reference"] = reference
                if not vals.get("name") or vals.get("name") in ("New", "Mới"):
                    vals["name"] = reference
        return super().create(vals_list)

    @api.depends("order_line.menu_item_id", "order_line.product_uom_qty")
    def _compute_total_meals(self):
        for order in self:
            order.total_meals = sum(
                order.order_line.filtered("menu_item_id").mapped("product_uom_qty")
            )

    @api.depends("kitchen_plan_ids")
    def _compute_kitchen_plan_count(self):
        for order in self:
            order.kitchen_plan_count = len(order.kitchen_plan_ids)

    @api.onchange("partner_id")
    def _onchange_partner_delivery_address(self):
        for order in self:
            today = fields.Date.context_today(order)
            if order.contract_id and (
                order.contract_id.client_id != order.partner_id
                or order.contract_id.status != "active"
                or order.contract_id.date_start > today
                or not order.contract_id.date_end
                or order.contract_id.date_end < today
            ):
                order.contract_id = False
            if not order.partner_id:
                order.partner_shipping_id = False
                continue
            delivery_address = self.env["res.partner"].search(
                [
                    ("parent_id", "=", order.partner_id.id),
                    ("type", "=", "delivery"),
                    ("active", "=", True),
                ],
                order="id",
                limit=1,
            )
            order.partner_shipping_id = delivery_address or order.partner_id

    @api.onchange("contract_id")
    def _onchange_contract_id_fill_order_lines(self):
        for order in self:
            if not order.contract_id:
                continue

            commands = [Command.clear()]
            missing_products = []
            for task in order.contract_id.task_ids:
                menu_item = self.env["set_top_menu.menu.item"].search(
                    [
                        ("product_id", "=", task.product_id.id),
                        ("active", "=", True),
                    ],
                    limit=1,
                )
                if not menu_item:
                    missing_products.append(task.product_id.display_name)
                    continue

                menu_item._ensure_sale_product()
                commands.append(
                    Command.create(
                        {
                            "menu_item_id": menu_item.id,
                            "contract_task_id": task.id,
                            "meal_type_id": menu_item.meal_type_ids[:1].id,
                            "product_id": menu_item.product_id.id,
                            "product_uom": (
                                task.product_uom_id.id or menu_item.product_id.uom_id.id
                            ),
                            "product_uom_qty": task.quantity,
                            "price_unit": task.price_unit,
                            "name": menu_item.name,
                            "catering_note": False,
                            "tax_id": [Command.clear()],
                        }
                    )
                )
            order.order_line = commands

            if missing_products:
                return {
                    "warning": {
                        "title": "Không tìm thấy món ăn",
                        "message": (
                            "Các sản phẩm sau chưa được liên kết với Món ăn nên không thể "
                            "thêm vào đơn hàng: %s"
                        )
                        % ", ".join(missing_products),
                    }
                }

    def action_confirm(self):
        self._check_kitchen_editable()
        self._check_selected_contract_validity()
        self._ensure_menu_line_accountable_fields()
        orders_to_confirm = self.filtered(lambda order: order.state in ("draft", "sent"))
        result = True
        if orders_to_confirm:
            result = super(SaleOrder, orders_to_confirm).action_confirm()

        # A confirmed order may be edited and confirmed again. Rebuild only plans
        # which have not entered production so Kitchen always receives fresh data.
        plans_to_replace = self.mapped("kitchen_plan_ids").filtered(
            lambda plan: plan.state in ("draft", "confirmed")
        )
        plans_to_replace.unlink()
        self.write({"catering_state": "confirmed"})
        self._create_kitchen_plans()
        return result

    @api.constrains("partner_id", "contract_id")
    def _check_selected_contract_validity(self):
        for order in self.filtered("contract_id"):
            today = fields.Date.context_today(order)
            contract = order.contract_id
            if contract.client_id != order.partner_id:
                raise UserError("Hợp đồng không thuộc khách hàng đã chọn.")
            if (
                contract.status != "active"
                or contract.date_start > today
                or not contract.date_end
                or contract.date_end < today
            ):
                raise UserError("Hợp đồng đã chọn không còn trong thời gian hiệu lực.")

    def _is_kitchen_locked(self):
        self.ensure_one()
        return bool(
            self.kitchen_plan_ids.filtered(lambda plan: plan.state in ("progress", "done"))
            or self.catering_state in ("in_production", "ready", "dispatched", "delivered")
        )

    def _check_kitchen_editable(self):
        if self.filtered(lambda order: order._is_kitchen_locked()):
            raise UserError(
                "Không thể chỉnh sửa đơn hàng vì bếp đã bắt đầu thực hiện đơn này."
            )

    def _ensure_menu_line_accountable_fields(self):
        """Complete hidden Sale fields before Odoo validates accountable lines."""
        for line in self.order_line.filtered(
            lambda order_line: not order_line.display_type and order_line.menu_item_id
        ):
            menu_item = line.menu_item_id
            menu_item._ensure_sale_product()
            values = {}
            if not line.product_id:
                values["product_id"] = menu_item.product_id.id
            if not line.product_uom:
                values["product_uom"] = menu_item.product_id.uom_id.id
            if not line.name:
                values["name"] = menu_item.name
            if line.tax_id:
                values["tax_id"] = [Command.clear()]
            if values:
                line.write(values)

    def _create_kitchen_plans(self):
        Plan = self.env["set_top_menu.kitchen.plan"]
        for order in self:
            menu_lines = order.order_line.filtered(
                lambda line: not line.display_type and line.menu_item_id
            )
            if not menu_lines or order.kitchen_plan_ids:
                continue
            missing_meal = menu_lines.filtered(lambda line: not line.meal_type_id)
            if missing_meal:
                raise UserError("Vui lòng chọn Loại bữa ăn cho tất cả các món trước khi xác nhận.")

            production_date = (
                order.commitment_date.date()
                if order.commitment_date
                else fields.Date.context_today(order)
            )
            for meal_type in menu_lines.mapped("meal_type_id"):
                lines = menu_lines.filtered(lambda line: line.meal_type_id == meal_type)
                Plan.create(
                    {
                        "production_date": production_date,
                        "meal_type_id": meal_type.id,
                        "company_id": order.company_id.id,
                        "state": "confirmed",
                        "order_ids": [Command.link(order.id)],
                        "line_ids": [
                            Command.create(
                                {
                                    "menu_item_id": line.menu_item_id.id,
                                    "quantity": line.product_uom_qty,
                                }
                            )
                            for line in lines
                        ],
                    }
                )

    def action_dispatch(self):
        invalid = self.filtered(lambda order: order.catering_state != "ready")
        if invalid:
            raise UserError("Chỉ có thể xuất giao đơn hàng đang ở trạng thái Sẵn sàng.")
        self.write({"catering_state": "dispatched"})

    def action_deliver(self):
        invalid = self.filtered(lambda order: order.catering_state != "dispatched")
        if invalid:
            raise UserError("Chỉ có thể hoàn tất giao hàng sau khi đã xuất giao.")
        self.write({"catering_state": "delivered"})

    def action_view_kitchen_plans(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("set_top_menu.action_kitchen_plans")
        action["domain"] = [("id", "in", self.kitchen_plan_ids.ids)]
        return action

    def action_cancel(self):
        result = super().action_cancel()
        self.write({"catering_state": "cancelled"})
        return result

    def action_draft(self):
        result = super().action_draft()
        self.write({"catering_state": "draft"})
        return result

    def action_open_fetch_wizard(self):
        """Nút Lấy ĐH: mở popup nhập tham số lấy đơn hàng từ HNCK."""
        form_view = self.env.ref("set_top_menu.view_order_fetch_wizard_form")
        return {
            "type": "ir.actions.act_window",
            "name": _("Lấy đơn hàng từ HNCK"),
            "res_model": "set_top_menu.order.fetch.wizard",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "target": "new",
        }

    @api.model
    def _order_fetch_params(
        self, page=1, per_page=20, status="DANG_GIAO",
        date_from=False, date_to=False, order_code=False, school_id=False,
    ):
        """Dựng query params ``supplier/orders`` (trống thì bỏ param)."""
        params = {"per_page": per_page}
        if page:
            params["page"] = page
        if status:
            params["status"] = status
        if order_code:
            params["code"] = order_code
        if school_id:
            params["school_id"] = school_id
        if date_from:
            params["order_date_from"] = str(date_from)
        if date_to:
            params["order_date_to"] = str(date_to)
        return params

    def fetch_supplier_orders(
        self, page=1, per_page=20, status="DANG_GIAO",
        date_from=False, date_to=False, order_code=False, school_id=False,
        x_nonce=False, x_timestamp=False,
    ):
        """Lấy đơn hàng từ HNCK rồi tạo/cập nhật đơn hàng hằng ngày."""
        params = self._order_fetch_params(
            page=page,
            per_page=per_page,
            status=status,
            date_from=date_from,
            date_to=date_to,
            order_code=order_code,
            school_id=school_id,
        )
        sign_kwargs = {}
        if x_nonce:
            sign_kwargs["x_nonce"] = x_nonce
        if x_timestamp:
            sign_kwargs["x_timestamp"] = x_timestamp
        result = HnckClient(self.env).fetch_supplier_orders(
            params, **sign_kwargs
        )
        if not isinstance(result, dict):
            raise UserError(_("API đơn hàng không trả về dữ liệu hợp lệ."))
        if result.get("success") is False:
            raise UserError(
                _("HNCK báo lỗi lấy đơn hàng: %s")
                % (result.get("message") or _("Không rõ nguyên nhân."))
            )
        payloads = result.get("data") or []
        if not isinstance(payloads, list):
            raise UserError(_("API đơn hàng không trả về danh sách đơn hàng."))
        counts = {
            "fetched": len(payloads),
            "total": (result.get("pagination") or {}).get("total")
            or len(payloads),
            "created": 0,
            "updated": 0,
            "skipped_no_code": 0,
            "skipped_locked": 0,
            "lines_ok": 0,
            "lines_skipped": 0,
            "partners_created": 0,
        }
        for payload in payloads:
            if isinstance(payload, dict):
                self._crall_upsert_order(payload, counts)
            else:
                counts["skipped_no_code"] += 1
        return counts

    @api.model
    def _crall_upsert_order(self, payload, counts):
        code = self._order_value(payload, "code", "order_code", "ma_don_hang")
        code = str(code).strip() if code not in (None, "") else ""
        if not code:
            counts["skipped_no_code"] += 1
            return
        order = self.search([("catering_reference", "=", code)], limit=1)
        if order and order._is_kitchen_locked():
            counts["skipped_locked"] += 1
            return
        partner = self._crall_order_partner(payload.get("school"), counts)
        line_commands = []
        products = payload.get("products") or []
        if not isinstance(products, list):
            products = []
        for item in products:
            if not isinstance(item, dict):
                counts["lines_skipped"] += 1
                continue
            item_code = self._order_value(
                item, "code", "product_code", "ma_san_pham"
            )
            item_code = (
                str(item_code).strip()
                if item_code not in (None, "")
                else ""
            )
            template = (
                self._match_food_template(item_code) if item_code else None
            )
            if not template:
                counts["lines_skipped"] += 1
                continue
            raw_qty = self._order_value(
                item,
                "quantity",
                "qty",
                "so_luong",
                "product_uom_qty",
            )
            try:
                quantity = float(raw_qty if raw_qty not in (None, "") else 1)
            except (TypeError, ValueError):
                quantity = 1.0
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "product_id": template.product_variant_id.id,
                        "product_uom_qty": quantity,
                    },
                )
            )
            counts["lines_ok"] += 1
        provided_date = self._crall_order_date(payload)
        order_vals = {
            "partner_id": partner.id,
            "commitment_date": fields.Datetime.now(),
            "order_line": ([(5, 0, 0)] if order else []) + line_commands,
        }
        if provided_date or not order:
            order_vals["date_order"] = provided_date or fields.Date.today()
        if order:
            order.write(order_vals)
            counts["updated"] += 1
        else:
            order_vals["catering_reference"] = code
            self.create(order_vals)
            counts["created"] += 1

    @api.model
    def _crall_order_partner(self, school, counts):
        Partner = self.env["res.partner"]
        name = ""
        if isinstance(school, dict):
            name = self._order_value(
                school, "name", "school_name", "display_name", "title"
            )
            name = str(name).strip() if name not in (None, "") else ""
        if name:
            partner = Partner.search([("name", "=", name)], limit=1)
            if partner:
                return partner
        else:
            partner = Partner.search(
                [("name", "=", _("Khách hàng HNCK"))], limit=1
            )
            if partner:
                return partner
            name = _("Khách hàng HNCK")
        counts["partners_created"] += 1
        return Partner.create(
            {"name": name, "is_company": True, "customer_rank": 1}
        )

    @api.model
    def _match_food_template(self, code):
        templates = self.env["product.template"]
        if not code:
            return templates.browse()
        domain = [
            "|",
            ("default_code", "=", code),
            ("crall_supplier_code", "=", code),
        ]
        return templates.search(
            domain + [("crall_food_source", "=", "foods")], limit=1
        ) or templates.search(domain, limit=1)

    @staticmethod
    def _crall_order_date(payload):
        """Ngày tạo đơn từ API (False khi thiếu/không đọc được)."""
        raw = SaleOrder._order_value(
            payload,
            "order_date",
            "created_at",
            "create_date",
            "date_order",
            "ngay_tao",
        )
        if raw in (None, ""):
            return False
        try:
            return fields.Date.from_string(str(raw).strip()[:10])
        except ValueError:
            return False

    @staticmethod
    def _order_value(payload, *keys, **kwargs):
        default = kwargs.get("default")
        if not isinstance(payload, dict):
            return default
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value
        return default

    def write(self, vals):
        # Kitchen state synchronization must remain possible after production starts,
        # while all user-editable business data is protected at model level.
        if set(vals) - {"catering_state"}:
            self._check_kitchen_editable()
        return super().write(vals)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    menu_item_id = fields.Many2one(
        "set_top_menu.menu.item",
        string="Món ăn",
        domain="[('active', '=', True)]",
        ondelete="restrict",
        index=True,
        help="Danh sách được lấy trực tiếp từ các món đã tạo tại màn hình Thực đơn.",
    )
    meal_type_id = fields.Many2one("set_top_menu.meal.type", string="Loại bữa ăn")
    contract_task_id = fields.Many2one(
        "set_top_menu.client.contract.task",
        string="Chi tiết hợp đồng",
        copy=False,
        ondelete="restrict",
    )
    catering_note = fields.Char(string="Ghi chú")

    @api.onchange("product_uom_qty", "contract_task_id")
    def _onchange_contract_quantity_keep_price(self):
        for line in self.filtered("contract_task_id"):
            line.price_unit = line.contract_task_id.price_unit

    @api.constrains("contract_task_id", "price_unit")
    def _check_contract_price(self):
        for line in self.filtered("contract_task_id"):
            rounding = line.currency_id.rounding or 0.01
            if float_compare(
                line.price_unit,
                line.contract_task_id.price_unit,
                precision_rounding=rounding,
            ):
                raise ValidationError(
                    "Đơn giá của món ăn phải giữ nguyên theo chi tiết hợp đồng."
                )

    @api.onchange("menu_item_id")
    def _onchange_menu_item_id(self):
        for line in self:
            if line.menu_item_id:
                menu_item = line.menu_item_id
                menu_item._ensure_sale_product()
                line.product_id = menu_item.product_id
                line.product_uom = menu_item.product_id.uom_id
                line.price_unit = (
                    line.contract_task_id.price_unit
                    if line.contract_task_id
                    else menu_item.sale_price
                )
                line.tax_id = [Command.clear()]
                line.meal_type_id = (
                    menu_item.meal_type_ids
                    if len(menu_item.meal_type_ids) == 1
                    else False
                )
            else:
                line.meal_type_id = False

    @api.onchange("product_id")
    def _onchange_product_id_set_menu_item(self):
        for line in self:
            if not line.product_id:
                line.menu_item_id = False
                line.meal_type_id = False
                continue
            if line.menu_item_id.product_id != line.product_id:
                line.menu_item_id = self.env["set_top_menu.menu.item"].search(
                    [("product_id", "=", line.product_id.id)], limit=1
                )
            line.meal_type_id = (
                line.menu_item_id.meal_type_ids
                if len(line.menu_item_id.meal_type_ids) == 1
                else False
            )

    @api.onchange("product_template_id")
    def _onchange_product_template_id_set_menu_item(self):
        for line in self:
            if not line.product_template_id:
                line.menu_item_id = False
                line.meal_type_id = False
                continue

            domain = [
                ("product_id.product_tmpl_id", "=", line.product_template_id.id),
                ("active", "=", True),
            ]
            if (
                line.product_id
                and line.product_id.product_tmpl_id == line.product_template_id
            ):
                domain.append(("product_id", "=", line.product_id.id))

            line.menu_item_id = self.env["set_top_menu.menu.item"].search(
                domain, limit=1
            )
            line.meal_type_id = (
                line.menu_item_id.meal_type_ids
                if len(line.menu_item_id.meal_type_ids) == 1
                else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("order_id"):
                order = self.env["sale.order"].browse(vals["order_id"])
                order._check_kitchen_editable()
                if order.contract_id:
                    contract_task = self.env["set_top_menu.client.contract.task"].browse(
                        vals.get("contract_task_id")
                    )
                    if not contract_task or contract_task.contract_id != order.contract_id:
                        raise UserError(
                            "Không thể thêm sản phẩm hoặc món ăn vào đơn hàng theo hợp đồng."
                        )
            if vals.get("menu_item_id"):
                menu_item = self.env["set_top_menu.menu.item"].browse(vals["menu_item_id"])
                menu_item._ensure_sale_product()
                if not vals.get("product_id"):
                    vals["product_id"] = menu_item.product_id.id
                if not vals.get("product_uom"):
                    vals["product_uom"] = menu_item.product_id.uom_id.id
                if not vals.get("name"):
                    vals["name"] = menu_item.name
                vals.setdefault("price_unit", menu_item.sale_price)
                vals["tax_id"] = [Command.clear()]
            if vals.get("contract_task_id"):
                contract_task = self.env["set_top_menu.client.contract.task"].browse(
                    vals["contract_task_id"]
                )
                vals["price_unit"] = contract_task.price_unit
        return super().create(vals_list)

    def write(self, vals):
        self.mapped("order_id")._check_kitchen_editable()
        contract_locked_fields = {
            "product_id",
            "product_template_id",
            "menu_item_id",
            "meal_type_id",
            "product_uom",
            "price_unit",
            "discount",
            "tax_id",
            "name",
            "catering_note",
        }
        if contract_locked_fields.intersection(vals) and self.filtered(
            lambda line: line.order_id.contract_id
        ):
            raise UserError(
                "Không thể thay đổi chi tiết của đơn hàng theo hợp đồng."
            )
        if len(self) == 1:
            contract_task = (
                self.env["set_top_menu.client.contract.task"].browse(vals["contract_task_id"])
                if vals.get("contract_task_id")
                else self.contract_task_id
            )
            if contract_task:
                vals = {**vals, "price_unit": contract_task.price_unit}
        if vals.get("menu_item_id"):
            menu_item = self.env["set_top_menu.menu.item"].browse(vals["menu_item_id"])
            menu_item._ensure_sale_product()
            vals = dict(vals)
            if not vals.get("product_id"):
                vals["product_id"] = menu_item.product_id.id
            if not vals.get("product_uom"):
                vals["product_uom"] = menu_item.product_id.uom_id.id
            if not vals.get("name"):
                vals["name"] = menu_item.name
            vals["tax_id"] = [Command.clear()]
        return super().write(vals)

    def unlink(self):
        self.mapped("order_id")._check_kitchen_editable()
        return super().unlink()

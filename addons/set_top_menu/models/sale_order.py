from urllib.parse import quote

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

from odoo.addons.crall_material.models.hnck_client import HnckClient

# URL truy xuất nguồn gốc đơn HNCK (%s = mã đơn hàng nội bộ).
HNCK_TRACE_URL = (
    "https://tracuu.hanoicheck.com.vn/NCC-2026-000432/truy-xuat/%s"
)

# Dòng đơn HNCK chưa xác nhận (draft) được sửa trực tiếp 2 trường này.
HNCK_DRAFT_EDITABLE_LINE_FIELDS = frozenset({"price_unit", "catering_note"})

# Trạng thái HNCK đang/đã giao: lưu người vận chuyển để thống kê.
HNCK_DELIVERING_STATUSES = frozenset(
    {"DANG_GIAO", "DA_GIAO", "GIAO_HANG_THANH_CONG"}
)

# Map trạng thái đơn HNCK -> catering_state nội bộ (TRA_HANG cố ý
# vắng mặt: giữ nguyên trạng thái hiện tại).
HNCK_ORDER_STATE_MAP = {
    "CHO_XAC_NHAN": "draft",
    "TU_CHOI": "cancelled",
    "DANG_CHUAN_BI": "in_production",
    "DANG_GIAO": "dispatched",
    "DA_GIAO": "delivered",
    "GIAO_HANG_THANH_CONG": "delivered",
    "HUY": "cancelled",
}


class SaleOrder(models.Model):
    _inherit = "sale.order"
    _rec_name = "catering_reference"

    catering_reference = fields.Char(
        string="Mã đơn phục vụ", required=True, copy=False, default="Mới"
    )
    catering_state = fields.Selection(
        [
            ("draft", "Chờ xác nhận"),
            ("confirmed", "Đã xác nhận"),
            ("in_production", "Đang chuẩn bị"),
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
    hnck_order = fields.Boolean(
        string="Đơn HNCK",
        default=False,
        readonly=True,
        copy=False,
        index=True,
        help="Đơn lấy về từ HNCK qua nút Lấy ĐH; chỉ được cập nhật qua API.",
    )
    transporter_id = fields.Many2one(
        "set_top_menu.delivery.staff",
        string="Người vận chuyển",
        readonly=True,
        copy=False,
        index=True,
    )
    stock_deducted = fields.Boolean(
        string="Đã trừ kho",
        default=False,
        readonly=True,
        copy=False,
    )
    contract_id = fields.Many2one(
        "set_top_menu.client.contract",
        string="Hợp đồng",
        domain="[('client_id', '=', partner_id), ('status', '=', 'active'), "
        "('date_start', '<=', context_today()), "
        "('date_end', '>=', context_today())]",
        ondelete="restrict",
    )
    catering_tax_id = fields.Many2one(
        "account.tax",
        string="Thuế",
        domain="[('type_tax_use', '=', 'sale')]",
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
                                task.product_uom_id.id or menu_item._order_line_uom().id
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

    @api.onchange("catering_tax_id")
    def _onchange_catering_tax_id(self):
        self._sync_line_taxes()

    def _sync_line_taxes(self):
        """Đồng bộ thuế các dòng theo thuế đơn (trống thì xóa)."""
        for order in self:
            target = set(order.catering_tax_id.ids)
            lines = order.order_line.filtered(
                lambda line: not line.display_type
                and set(line.tax_id.ids) != target
            )
            if lines:
                lines.write({"tax_id": [(6, 0, list(target))]})

    def action_open_traceability_qr(self):
        """Nút QR truy xuất (chỉ đơn HNCK): mở trang truy xuất ở tab mới."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": HNCK_TRACE_URL % quote(self.catering_reference or ""),
            "target": "new",
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
        if self.env.context.get("hnck_sync"):
            return
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
        if self.env.context.get("hnck_sync"):
            return
        if self.filtered(lambda order: order._is_kitchen_locked()):
            raise UserError(
                "Không thể chỉnh sửa đơn hàng vì bếp đã bắt đầu thực hiện đơn này."
            )

    def _check_hnck_editable(self):
        if self.env.context.get("hnck_sync"):
            return
        if self.filtered("hnck_order"):
            raise UserError(
                "Đơn hàng HNCK chỉ được cập nhật qua nút Lấy ĐH, "
                "không được chỉnh sửa trực tiếp trên hệ thống."
            )

    def _ensure_menu_line_accountable_fields(self):
        """Complete hidden Sale fields before Odoo validates accountable lines."""
        self._sync_line_taxes()
        for line in self.order_line.filtered(
            lambda order_line: not order_line.display_type and order_line.menu_item_id
        ):
            menu_item = line.menu_item_id
            menu_item._ensure_sale_product()
            values = {}
            if not line.product_id:
                values["product_id"] = menu_item.product_id.id
            if not line.product_uom:
                values["product_uom"] = menu_item._order_line_uom().id
            if not line.name:
                values["name"] = menu_item.name
            if values:
                line.write(values)

    def _create_kitchen_plans(self):
        Plan = self.env["set_top_menu.kitchen.plan"]
        lunch = self.env.ref("set_top_menu.meal_type_lunch")
        for order in self:
            menu_lines = order.order_line.filtered(
                lambda line: not line.display_type and line.menu_item_id
            )
            if not menu_lines or order.kitchen_plan_ids:
                continue
            lines_by_meal = {}
            for line in menu_lines:
                meal = line.meal_type_id or lunch
                lines_by_meal.setdefault(meal, []).append(line)

            production_date = (
                order.commitment_date.date()
                if order.commitment_date
                else fields.Date.context_today(order)
            )
            for meal_type, lines in lines_by_meal.items():
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

    def action_start_preparation(self):
        invalid = self.filtered(lambda order: order.catering_state != "confirmed")
        if invalid:
            raise UserError(
                "Chỉ có thể chuyển chuẩn bị đơn hàng đang ở trạng thái Đã xác nhận."
            )
        short = self.filtered(
            lambda order: not order.hnck_order and order._has_stock_shortage()
        )
        if short:
            if len(self) > 1:
                raise UserError(
                    "Các đơn hàng sau thiếu tồn kho, vui lòng xử lý từng đơn: %s."
                    % ", ".join(short.mapped("catering_reference"))
                )
            return short._open_shortage_wizard()
        self.filtered(lambda order: not order.hnck_order)._create_kitchen_plans()
        self.filtered(lambda order: not order.hnck_order)._deduct_order_stock()
        self.write({"catering_state": "in_production"})

    def _order_product_stock(self):
        """Tồn kho theo sản phẩm cho các dòng thực phẩm (trừ món ăn, dịch vụ)."""
        self.ensure_one()
        company = self.company_id
        totals = {}
        for line in self.order_line.filtered(
            lambda order_line: not order_line.display_type
            and order_line.product_id
            and not order_line.menu_item_id
            and order_line.product_id.type != "service"
        ):
            product = line.product_id
            # Bỏ qua kiểm tra cùng loại đơn vị: khác loại thì dùng nguyên số.
            required = (line.product_uom or product.uom_id)._compute_quantity(
                line.product_uom_qty, product.uom_id, raise_if_failure=False
            )
            totals[product] = totals.get(product, 0.0) + required
        stock = {}
        for product, required in totals.items():
            available = product.with_company(company).qty_available
            stock[product] = {
                "required": required,
                "available": available,
                "shortage": required - available,
            }
        return stock

    def _has_stock_shortage(self):
        self.ensure_one()
        for product, vals in self._order_product_stock().items():
            rounding = product.uom_id.rounding or 0.01
            if (
                float_compare(vals["shortage"], 0.0, precision_rounding=rounding)
                > 0
            ):
                return True
        return False

    def _order_stock_location(self):
        self.ensure_one()
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if warehouse:
            return warehouse.lot_stock_id
        return self.env.ref("stock.stock_location_stock")

    def _apply_order_stock(self, factor):
        for order in self:
            location = order._order_stock_location()
            for product, vals in order._order_product_stock().items():
                if vals["required"]:
                    self.env["stock.quant"]._update_available_quantity(
                        product.with_company(order.company_id),
                        location,
                        factor * vals["required"],
                    )

    def _deduct_order_stock(self):
        todo = self.filtered(lambda order: not order.stock_deducted)
        todo._apply_order_stock(-1)
        todo.write({"stock_deducted": True})

    def _return_order_stock(self):
        todo = self.filtered(lambda order: order.stock_deducted)
        todo._apply_order_stock(1)
        todo.write({"stock_deducted": False})

    def _open_shortage_wizard(self):
        self.ensure_one()
        lines = [
            "Đơn hàng %s còn thiếu tồn kho:"
            % (self.catering_reference or self.name)
        ]
        for product, vals in self._order_product_stock().items():
            rounding = product.uom_id.rounding or 0.01
            if (
                float_compare(vals["shortage"], 0.0, precision_rounding=rounding)
                <= 0
            ):
                continue
            lines.append(
                "- %s: cần %g, tồn %g, thiếu %g %s"
                % (
                    product.display_name,
                    vals["required"],
                    vals["available"],
                    vals["shortage"],
                    product.uom_id.name,
                )
            )
        wizard = self.env["set_top_menu.order.shortage.wizard"].create(
            {"order_id": self.id, "message": "\n".join(lines)}
        )
        form_view = self.env.ref("set_top_menu.view_order_shortage_wizard_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Yêu cầu mua hàng",
            "res_model": "set_top_menu.order.shortage.wizard",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "res_id": wizard.id,
            "target": "new",
        }

    def action_cancel_preparation(self):
        invalid = self.filtered(
            lambda order: order.catering_state != "in_production"
        )
        if invalid:
            raise UserError(
                "Chỉ có thể huỷ chuẩn bị đơn hàng đang ở trạng thái Đang chuẩn bị."
            )
        linked = self.filtered("kitchen_plan_ids")
        if linked:
            raise UserError(
                "Không thể huỷ chuẩn bị vì đơn hàng đã có lệnh sản xuất: %s."
                % ", ".join(linked.mapped("kitchen_plan_ids.name"))
            )
        self.write({"catering_state": "confirmed"})
        self.filtered(lambda order: not order.hnck_order)._return_order_stock()

    def action_cancel_order(self):
        invalid = self.filtered(
            lambda order: order.catering_state not in ("draft", "confirmed")
        )
        if invalid:
            raise UserError(
                "Chỉ có thể huỷ đơn hàng đang ở trạng thái "
                "Chờ xác nhận hoặc Đã xác nhận."
            )
        self.write({"catering_state": "cancelled"})

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

    def action_back_to_order_list(self):
        """Nút Quay lại trên form: mở lại màn hình danh sách đơn hàng."""
        self.ensure_one()
        return self.env.ref("set_top_menu.action_daily_orders").read()[0]

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
        result = HnckClient(self.env).fetch_supplier_orders(params)
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
            "skipped_manual": 0,
            "lines_ok": 0,
            "lines_skipped": 0,
            "partners_created": 0,
            "staff_created": 0,
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
        if order and not order.hnck_order:
            counts["skipped_manual"] += 1
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
        api_status = self._order_value(
            payload, "status", "order_status", "trang_thai"
        )
        api_status = (
            str(api_status).strip().upper()
            if api_status not in (None, "")
            else ""
        )
        order_vals = {
            "partner_id": partner.id,
            "commitment_date": fields.Datetime.now(),
            "order_line": ([(5, 0, 0)] if order else []) + line_commands,
        }
        mapped_state = HNCK_ORDER_STATE_MAP.get(api_status)
        if mapped_state:
            order_vals["catering_state"] = mapped_state
        if api_status in HNCK_DELIVERING_STATUSES:
            transporter = self._crall_order_transporter(payload, counts)
            if transporter:
                order_vals["transporter_id"] = transporter.id
        if provided_date or not order:
            order_vals["date_order"] = provided_date or fields.Date.today()
        if order:
            order.with_context(hnck_sync=True).write(order_vals)
            counts["updated"] += 1
        else:
            order_vals["catering_reference"] = code
            order_vals["hnck_order"] = True
            self.with_context(hnck_sync=True).create(order_vals)
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
    def _crall_order_transporter(self, payload, counts):
        info = self._order_value(
            payload,
            "transporter",
            "shipper",
            "driver",
            "delivery_staff",
            "delivery_man",
            "nguoi_van_chuyen",
            "nguoi_giao_hang",
        )
        if isinstance(info, str):
            info = {"name": info}
        if not isinstance(info, dict):
            return self.env["set_top_menu.delivery.staff"].browse()
        name = self._order_value(
            info, "name", "full_name", "display_name", "title", "ten", "ho_ten"
        )
        name = str(name).strip() if name not in (None, "") else ""
        code = self._order_value(
            info, "code", "staff_code", "driver_code", "ma", "ma_nhan_vien"
        )
        code = str(code).strip() if code not in (None, "") else ""
        phone = self._order_value(
            info, "phone", "phone_number", "mobile", "sdt", "dien_thoai"
        )
        phone = str(phone).strip() if phone not in (None, "") else ""
        if not name and not code:
            return self.env["set_top_menu.delivery.staff"].browse()
        Staff = self.env["set_top_menu.delivery.staff"]
        staff = Staff.browse()
        if code:
            staff = Staff.search([("code", "=", code)], limit=1)
        if not staff and name:
            staff = Staff.search([("name", "=", name)], limit=1)
        if staff:
            return staff
        counts["staff_created"] += 1
        return Staff.create(
            {"name": name or code, "code": code or False, "phone": phone or False}
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
        if "catering_reference" in vals and not self.env.context.get(
            "hnck_sync"
        ):
            for order in self:
                if vals["catering_reference"] != order.catering_reference:
                    raise UserError(
                        "Không được thay đổi mã đơn hàng sau khi đã tạo."
                    )
        if set(vals) - {"catering_state"}:
            self._check_kitchen_editable()
            self._check_hnck_editable()
        result = super().write(vals)
        if "catering_tax_id" in vals:
            self._sync_line_taxes()
        return result


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
    product_stock_qty = fields.Float(
        string="Tồn kho",
        related="product_id.qty_available",
        readonly=True,
    )
    catering_line_type = fields.Selection(
        [("dish", "Món ăn"), ("food", "Thực phẩm")],
        string="Loại",
        compute="_compute_catering_line_type",
    )

    @api.depends("menu_item_id", "product_id")
    def _compute_catering_line_type(self):
        for line in self:
            if line.menu_item_id:
                line.catering_line_type = "dish"
            elif line.product_id and not line.display_type:
                line.catering_line_type = "food"
            else:
                line.catering_line_type = False
    # Đổi số lượng không được tính lại đơn giá. Odoo cộng dồn @api.depends
    # của method gốc và method override nên phải trỏ compute sang method mới
    # thì mới gỡ được phụ thuộc product_uom_qty (các thuộc tính khác của
    # field được kế thừa nguyên từ sale.order.line).
    price_unit = fields.Float(compute="_compute_catering_price_unit")
    # Dropdown ĐVT dòng đơn xổ đủ danh sách như khi tạo món (gỡ lọc cùng
    # nhóm của Odoo lõi).
    product_uom = fields.Many2one(domain="[]")
    # Cột chọn Món ăn / Thực phẩm: trừ Thực phẩm chuẩn; món ăn lấy hết
    # (không kiểm tra cờ bán được), material còn lại phải tick bán được.
    product_template_id = fields.Many2one(
        domain="[\"&\", \"|\", "
        "(\"crall_food_source\", \"!=\", \"standard\"), "
        "(\"crall_food_source\", \"=\", False), \"|\", "
        "(\"is_menu_item_product\", \"=\", True), "
        "(\"sale_ok\", \"=\", True)]"
    )

    @api.depends("product_id")
    def _compute_product_uom(self):
        """ĐVT dòng đơn: món ăn theo Đơn vị khẩu phần, còn lại theo gốc."""
        dishes = self.filtered(
            lambda line: not line.display_type
            and line.menu_item_id
            and line.product_id
        )
        for line in dishes:
            line.product_uom = line.menu_item_id._order_line_uom()
        super(SaleOrderLine, self - dishes)._compute_product_uom()

    @api.depends("product_id", "product_uom")
    def _compute_catering_price_unit(self):
        """Đơn giá dòng đơn: giá hợp đồng > giá món > giá bảng giá.

        Chỉ tính lại khi đổi sản phẩm/ĐVT. Khác loại ĐVT thì dùng nguyên
        giá bán, không quy đổi để tránh lỗi cùng loại đơn vị.
        """
        for line in self.filtered(
            lambda record: not record.display_type and record.contract_task_id
        ):
            line.price_unit = line.contract_task_id.price_unit
        for line in self.filtered(
            lambda record: not record.display_type
            and not record.contract_task_id
            and record.menu_item_id
        ):
            line.price_unit = line.menu_item_id.sale_price
        rest = self.filtered(
            lambda record: not record.contract_task_id and not record.menu_item_id
        )
        for line in rest:
            if (
                line.product_id
                and line.product_uom
                and line.product_uom.category_id
                != line.product_id.uom_id.category_id
            ):
                line.price_unit = line.product_id.list_price
            else:
                super(SaleOrderLine, line)._compute_price_unit()

    def _compute_price_unit(self):
        """Alias giữ tương thích các luồng gọi trực tiếp method gốc."""
        return self._compute_catering_price_unit()

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
                line.product_uom = menu_item._order_line_uom()
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
            if line.menu_item_id and not line.contract_task_id:
                line.price_unit = line.menu_item_id.sale_price
            if not line.contract_task_id:
                line.product_uom = (
                    line.menu_item_id._order_line_uom()
                    if line.menu_item_id
                    else line.product_id.uom_id
                )

    @api.onchange("product_template_id")
    def _onchange_product_template_id_set_menu_item(self):
        for line in self:
            if not line.product_template_id:
                line.menu_item_id = False
                line.meal_type_id = False
                line.product_id = False
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
            if line.contract_task_id:
                continue
            if line.menu_item_id:
                line.menu_item_id._ensure_sale_product()
                line.product_id = line.menu_item_id.product_id
                line.product_uom = line.menu_item_id._order_line_uom()
                line.price_unit = line.menu_item_id.sale_price
            else:
                line.product_id = line.product_template_id.product_variant_id
                line.product_uom = line.product_template_id.uom_id
                line.price_unit = line.product_template_id.list_price

    def action_buy_product(self):
        """Mở phiếu mua mới cho đúng phần còn thiếu của dòng đơn."""
        self.ensure_one()
        company = self.order_id.company_id
        product = self.product_id.with_company(company)
        if not product:
            raise UserError("Dòng đơn hàng chưa có sản phẩm.")
        rounding = product.uom_id.rounding or 0.01
        line_uom = self.product_uom or product.uom_id
        required = line_uom._compute_quantity(
            self.product_uom_qty, product.uom_id, raise_if_failure=False
        )
        shortage = required - product.qty_available
        if float_compare(shortage, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(
                "Tồn kho đã đủ cho dòng đơn hàng này, không cần mua thêm."
            )
        po_uom = product.uom_po_id
        return {
            "type": "ir.actions.act_window",
            "name": "Mua hàng",
            "res_model": "purchase.order",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_company_id": company.id,
                "default_origin": self.order_id.catering_reference or False,
                "default_order_line": [
                    [
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "name": product.display_name,
                            "product_qty": product.uom_id._compute_quantity(
                                shortage, po_uom
                            ),
                            "product_uom": po_uom.id,
                            "price_unit": product.standard_price,
                            "date_planned": fields.Datetime.now(),
                        },
                    ]
                ],
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("order_id"):
                order = self.env["sale.order"].browse(vals["order_id"])
                order._check_kitchen_editable()
                order._check_hnck_editable()
                if order.contract_id and not self.env.context.get("hnck_sync"):
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
                    vals["product_uom"] = menu_item._order_line_uom().id
                if not vals.get("name"):
                    vals["name"] = menu_item.name
                vals.setdefault("price_unit", menu_item.sale_price)
                vals["tax_id"] = [Command.clear()]
            if not vals.get("product_id") and vals.get(
                "product_template_id"
            ):
                template = self.env["product.template"].browse(
                    vals["product_template_id"]
                )
                if template.exists() and template.product_variant_id:
                    vals["product_id"] = template.product_variant_id.id
            if vals.get("product_id") and (
                not vals.get("name") or not vals.get("product_uom")
            ):
                product = self.env["product.product"].browse(vals["product_id"])
                if product.exists():
                    if not vals.get("name"):
                        vals["name"] = (
                            product.get_product_multiline_description_sale()
                        )
                    if not vals.get("product_uom"):
                        vals["product_uom"] = product.uom_id.id
            if (
                not vals.get("menu_item_id")
                and "price_unit" not in vals
                and vals.get("product_id")
            ):
                product = self.env["product.product"].browse(vals["product_id"])
                if product.exists():
                    vals["price_unit"] = product.list_price
            if vals.get("contract_task_id"):
                contract_task = self.env["set_top_menu.client.contract.task"].browse(
                    vals["contract_task_id"]
                )
                vals["price_unit"] = contract_task.price_unit
        records = super().create(vals_list)
        records.mapped("order_id")._sync_line_taxes()
        return records

    def _check_hnck_line_editable(self, vals):
        """Đơn HNCK chưa xác nhận được sửa đơn giá và ghi chú dòng."""
        if self.env.context.get("hnck_sync"):
            return
        editable = self.filtered(
            lambda line: line.order_id.hnck_order
            and line.order_id.catering_state == "draft"
            and set(vals) <= HNCK_DRAFT_EDITABLE_LINE_FIELDS
        )
        (self - editable).mapped("order_id")._check_hnck_editable()

    def write(self, vals):
        self.mapped("order_id")._check_kitchen_editable()
        self._check_hnck_line_editable(vals)
        contract_locked_fields = {
            "product_id",
            "product_template_id",
            "menu_item_id",
            "meal_type_id",
            "product_uom",
            "price_unit",
            "discount",
            "name",
            "catering_note",
        }
        if (
            contract_locked_fields.intersection(vals)
            and not self.env.context.get("hnck_sync")
            and self.filtered(lambda line: line.order_id.contract_id)
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
                vals["product_uom"] = menu_item._order_line_uom().id
            if not vals.get("name"):
                vals["name"] = menu_item.name
        return super().write(vals)

    def unlink(self):
        self.mapped("order_id")._check_kitchen_editable()
        self.mapped("order_id")._check_hnck_editable()
        return super().unlink()

from urllib.parse import quote

from markupsafe import escape

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

# Trường client tự gửi kèm khi lưu dòng (force_save) nhưng phải giữ nguyên.
HNCK_LINE_COMPANION_FIELDS = frozenset(
    {
        "product_id",
        "product_template_id",
        "menu_item_id",
        "meal_type_id",
        "product_uom",
        "product_uom_qty",
        "discount",
        "name",
        "catering_note",
        "display_type",
        "sequence",
        "company_id",
        "currency_id",
        "contract_task_id",
    }
)

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
    hnck_price_editable = fields.Boolean(
        string="Cho sửa giá HNCK",
        default=False,
        readonly=True,
        copy=False,
        help="Bật qua nút Chỉnh sửa giá để cho phép sửa đơn giá lưới chi tiết đơn HNCK.",
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

        # Xác nhận chỉ chuyển trạng thái, không tạo lệnh sản xuất (kế hoạch
        # được tạo khi Chuẩn bị hoặc từ màn hình kế hoạch sản xuất).
        self.write({"catering_state": "confirmed"})
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

    def _hnck_grid_save_allowed(self, fields):
        """Form save chỉ đổi lưới dòng trên đơn HNCK draft/đã mở giá.

        Từng dòng vẫn bị khóa dòng kiểm tra; thêm/xóa dòng vẫn bị chặn
        ở create/unlink.
        """
        return (
            fields <= {"order_line"}
            and bool(self)
            and all(
                order.hnck_order
                and (
                    order.catering_state == "draft"
                    or order.hnck_price_editable
                )
                for order in self
            )
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
        """Tồn kho theo sản phẩm: chỉ dòng tồn kho (trừ món, dịch vụ, tiêu hao)."""
        self.ensure_one()
        company = self.company_id
        totals = {}
        for line in self.order_line.filtered(
            lambda order_line: not order_line.display_type
            and order_line.product_id
            and not order_line.menu_item_id
            and order_line.product_id.type == "product"
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

    def _check_cancel_allowed(self):
        invalid = self.filtered(
            lambda order: order.catering_state not in ("draft", "confirmed")
        )
        if invalid:
            raise UserError(
                "Chỉ có thể huỷ đơn hàng đang ở trạng thái "
                "Chờ xác nhận hoặc Đã xác nhận."
            )

    def action_cancel_order(self):
        """Nút Huỷ đơn: mở popup xác nhận + nhập lý do bắt buộc."""
        self._check_cancel_allowed()
        self.ensure_one()
        form_view = self.env.ref(
            "set_top_menu.view_order_cancel_wizard_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Lý do huỷ đơn"),
            "res_model": "set_top_menu.order.cancel.wizard",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "target": "new",
            "context": {"default_order_id": self.id},
        }

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
        if "currency_id" in vals and not self.env.context.get("hnck_sync"):
            for order in self:
                if (
                    vals["currency_id"] != order.currency_id.id
                    and order.catering_state != "draft"
                ):
                    raise UserError(
                        "Chỉ được đổi tiền tệ khi đơn hàng còn ở trạng thái "
                        "Chờ xác nhận."
                    )
        remaining = set(vals) - {"catering_state", "hnck_price_editable"}
        if remaining and not self._hnck_grid_save_allowed(remaining):
            self._check_kitchen_editable()
            self._check_hnck_editable()
        old_states = (
            {order.id: order.catering_state for order in self}
            if "catering_state" in vals
            else {}
        )
        result = super().write(vals)
        if "catering_tax_id" in vals:
            self._sync_line_taxes()
        if old_states:
            self._log_catering_state_changes(old_states)
        return result

    def _log_catering_state_changes(self, old_states):
        """Ghi mọi đổi trạng thái phục vụ vào cột hoạt động (ghi chú nội bộ)."""
        labels = dict(self._fields["catering_state"].selection)
        reason = (self.env.context.get("cancel_reason") or "").strip()
        for order in self:
            old = old_states.get(order.id)
            new = order.catering_state
            if old is None or old == new:
                continue
            body = "Trạng thái: %s → %s." % (
                labels.get(old, old),
                labels.get(new, new),
            )
            if new == "cancelled" and reason:
                body += "<br/>Lý do huỷ đơn: %s." % escape(reason).replace(
                    "\n", "<br/>"
                )
            order.message_post(body=body, subtype_xmlid="mail.mt_note")

    @property
    def _rec_names_search(self):
        return super()._rec_names_search + ["catering_reference"]

    def action_update_prices(self):
        """Cập nhật đơn giá theo giá gốc cho các đơn Chờ xác nhận."""
        targets = self.filtered(
            lambda order: not order.hnck_order
            and order.catering_state == "draft"
        )
        if not targets:
            raise UserError(
                _(
                    "Không có đơn Chờ xác nhận nào để cập nhật giá "
                    "(chỉ cập nhật đơn hệ thống ở trạng thái Chờ xác nhận)."
                )
            )
        targets.mapped("order_line")._compute_catering_price_unit()
        skipped = len(self) - len(targets)
        message = _("Đã cập nhật giá cho %s đơn hàng.") % len(targets)
        if skipped:
            message += " " + _(
                "Bỏ qua %s đơn không ở trạng thái Chờ xác nhận."
            ) % skipped
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Cập nhật giá"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def action_update_hnck_prices(self):
        """Cập nhật giá mới nhất cho dòng đơn HNCK.

        Đơn Chờ xác nhận: compute lại toàn bộ dòng (bỏ qua điều kiện
        đơn giá bằng 1). Các trạng thái khác: chỉ compute dòng có đơn
        giá bằng 1 (placeholder).
        """
        self.ensure_one()
        if not self.hnck_order:
            raise UserError("Chỉ đơn HNCK mới được cập nhật giá mới.")
        lines = self.order_line.filtered(lambda line: not line.display_type)
        if self.catering_state == "draft":
            targets = lines
        else:
            targets = lines.filtered(lambda line: line.price_unit == 1)
        if not targets:
            if self.catering_state == "draft":
                raise UserError(
                    "Đơn hàng chưa có dòng nào để cập nhật giá mới."
                )
            raise UserError(
                "Không có dòng nào có đơn giá bằng 1 để cập nhật giá mới."
            )
        targets.with_context(hnck_sync=True)._compute_catering_price_unit()
        message = "Đã cập nhật giá mới cho %s dòng." % len(targets)
        self.message_post(body=message)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Cập nhật giá mới",
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def action_enable_hnck_price_edit(self):
        """Bật sửa đơn giá lưới chi tiết cho đơn HNCK.

        Điều kiện: lưới chi tiết đang có ít nhất một dòng có đơn giá
        bằng 1. Sau khi bật, cho phép sửa đơn giá của tất cả sản phẩm
        trên lưới. Nút không ẩn sau khi nhấn nên gọi lại là idempotent.
        """
        self.ensure_one()
        if not self.hnck_order:
            raise UserError("Chỉ đơn HNCK mới được chỉnh sửa giá.")
        if self.hnck_price_editable:
            return True
        has_placeholder = any(
            not line.display_type and line.price_unit == 1
            for line in self.order_line
        )
        if not has_placeholder:
            raise UserError(
                "Chỉ được chỉnh sửa giá khi lưới chi tiết đang có "
                "đơn giá bằng 1."
            )
        self.write({"hnck_price_editable": True})
        return True

    def action_bulk_purchase(self):
        """Mở phiếu mua mới gom hàng mua trực tiếp và NVL món ăn."""
        orders = self.filtered(lambda order: order.catering_state != "cancelled")
        if not orders:
            raise UserError(
                "Không có đơn hàng nào để mua (chưa chọn đơn hoặc đơn đã huỷ)."
            )
        if len(orders.mapped("company_id")) > 1:
            raise UserError("Vui lòng chỉ chọn các đơn hàng cùng một khách hàng.")
        company = orders[0].company_id
        totals = {}
        contributors = self.env["sale.order"]
        for order in orders:
            added = False
            lines = order.order_line.filtered(
                lambda line: not line.display_type
                and line.product_id
                and line.product_uom_qty > 0
            )
            for line in lines:
                if line.menu_item_id:
                    added |= self._bulk_purchase_dish(line, company, totals)
                else:
                    added |= self._bulk_purchase_direct(line, company, totals)
            if added:
                contributors |= order
        if not totals:
            raise UserError(
                "Các đơn hàng đã chọn không có sản phẩm nào cần mua."
            )
        commands = [
            [
                0,
                0,
                {
                    "product_id": product.id,
                    "name": product.display_name,
                    "product_qty": quantity,
                    "product_uom": (product.uom_po_id or product.uom_id).id,
                    "price_unit": product.standard_price,
                    "date_planned": fields.Datetime.now(),
                },
            ]
            for product, quantity in totals.items()
        ]
        return {
            "type": "ir.actions.act_window",
            "name": "Mua hàng",
            "res_model": "purchase.order",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_company_id": company.id,
                "default_origin": ", ".join(
                    contributors.mapped("catering_reference")
                ),
                "default_order_line": commands,
            },
        }

    @api.model
    def _bulk_purchase_direct(self, line, company, totals):
        product = line.product_id.with_company(company)
        if product.type == "service":
            return False
        line_uom = line.product_uom or product.uom_id
        po_uom = product.uom_po_id or product.uom_id
        quantity = line_uom._compute_quantity(
            line.product_uom_qty, po_uom, raise_if_failure=False
        )
        totals[product] = totals.get(product, 0.0) + quantity
        return True

    @api.model
    def _bulk_purchase_dish(self, line, company, totals):
        added = False
        for ingredient in line.menu_item_id.ingredient_ids:
            product = ingredient.product_id.with_company(company)
            if not product or product.type == "service":
                continue
            required = ingredient.uom_id._compute_quantity(
                ingredient.quantity * line.product_uom_qty,
                product.uom_id,
                raise_if_failure=False,
            )
            po_uom = product.uom_po_id or product.uom_id
            quantity = product.uom_id._compute_quantity(
                required, po_uom, raise_if_failure=False
            )
            totals[product] = totals.get(product, 0.0) + quantity
            added = True
        return added


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

    @api.depends("product_id")
    def _compute_catering_price_unit(self):
        """Đơn giá tuyệt đối, không quy đổi tiền tệ: hợp đồng > món > giá bán.

        Chỉ tính lại khi đổi sản phẩm. ĐVT dòng đơn là đơn vị bán nên đổi
        ĐVT không tính lại giá; giá lấy nguyên con số đã nhập, kể cả khi
        có tỉ giá hay khác loại ĐVT (bỏ qua bảng giá Odoo).
        """
        for line in self:
            if (
                line.qty_invoiced > 0
                or (
                    line.product_id.expense_policy == "cost"
                    and line.is_expense
                )
                or line._is_discount_line()
            ):
                continue
            if line.display_type or not line.product_id:
                line.price_unit = 0.0
            elif line.contract_task_id:
                line.price_unit = line.contract_task_id.price_unit
            elif line.menu_item_id:
                line.price_unit = line.menu_item_id.sale_price
            else:
                line.price_unit = line.product_id.list_price

    def _compute_price_unit(self):
        """Alias giữ tương thích các luồng gọi trực tiếp method gốc."""
        return self._compute_catering_price_unit()

    @api.depends("product_id", "order_id.catering_tax_id")
    def _compute_tax_id(self):
        """Thuế dòng theo thuế đơn: chưa chọn thuế đơn thì dòng không thuế.

        Ghi đè logic gốc (lấy thuế mặc định của sản phẩm) để hàng Tiền thuế
        chỉ tính khi trường Thuế của đơn được chọn.
        """
        for line in self:
            if line.display_type:
                line.tax_id = False
            else:
                line.tax_id = line.order_id.catering_tax_id

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
            and (
                (
                    line.order_id.catering_state == "draft"
                    and line._hnck_only_allowed_changed(
                        vals, HNCK_DRAFT_EDITABLE_LINE_FIELDS
                    )
                )
                or (
                    line.order_id.hnck_price_editable
                    and line._hnck_only_allowed_changed(vals, {"price_unit"})
                )
            )
        )
        (self - editable).mapped("order_id")._check_hnck_editable()

    def _hnck_only_allowed_changed(self, vals, allowed):
        """Chỉ các trường cho phép được đổi giá trị.

        Client gửi kèm các trường force_save khi lưu dòng; các trường này
        phải giữ nguyên giá trị cũ.
        """
        self.ensure_one()
        for fname, new_value in vals.items():
            if fname in allowed:
                continue
            if fname not in HNCK_LINE_COMPANION_FIELDS:
                return False
            field = self._fields.get(fname)
            old_value = self[fname]
            if field is not None and field.type == "many2one":
                old_value = old_value.id or False
                new_value = new_value or False
            elif field is not None and field.type == "float":
                old_value = float(old_value or 0.0)
                new_value = float(new_value or 0.0)
            elif field is not None and field.type == "integer":
                old_value = int(old_value or 0)
                new_value = int(new_value or 0)
            elif field is not None and field.type == "boolean":
                old_value = bool(old_value)
                new_value = bool(new_value)
            elif field is not None and field.type in (
                "char",
                "text",
                "html",
                "selection",
            ):
                old_value = old_value or ""
                new_value = new_value or ""
            if old_value != new_value:
                return False
        return True

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

    # ĐVT bán độc lập ĐVT kho: 3 ghi đè dưới dung sai lệch nhóm ĐVT,
    # cùng nhóm giữ nguyên hành vi lõi sale_stock 17.0.

    @api.depends(
        "move_ids.state",
        "move_ids.scrapped",
        "move_ids.quantity",
        "move_ids.product_uom",
    )
    def _compute_qty_delivered(self):
        """Dòng lệch nhóm ĐVT kho quy đổi dung sai, còn lại chạy lõi."""
        special = self.filtered(
            lambda line: line.qty_delivered_method == "stock_move"
            and line.product_uom.category_id
            != line.product_id.uom_id.category_id
        )
        rest = self - special
        if rest:
            super(SaleOrderLine, rest)._compute_qty_delivered()
        for line in special:
            qty = 0.0
            outgoing_moves, incoming_moves = (
                line._get_outgoing_incoming_moves()
            )
            for move in outgoing_moves:
                if move.state != "done":
                    continue
                qty += move.product_uom._compute_quantity(
                    move.quantity,
                    line.product_uom,
                    rounding_method="HALF-UP",
                    raise_if_failure=False,
                )
            for move in incoming_moves:
                if move.state != "done":
                    continue
                qty -= move.product_uom._compute_quantity(
                    move.quantity,
                    line.product_uom,
                    rounding_method="HALF-UP",
                    raise_if_failure=False,
                )
            line.qty_delivered = qty

    def _get_qty_procurement(self, previous_product_uom_qty=False):
        """Quy đổi dung sai khi ĐVT bán lệch nhóm ĐVT kho."""
        self.ensure_one()
        qty = 0.0
        outgoing_moves, incoming_moves = self._get_outgoing_incoming_moves()
        for move in outgoing_moves:
            qty_to_compute = (
                move.quantity if move.state == "done" else move.product_uom_qty
            )
            qty += move.product_uom._compute_quantity(
                qty_to_compute,
                self.product_uom,
                rounding_method="HALF-UP",
                raise_if_failure=False,
            )
        for move in incoming_moves:
            qty_to_compute = (
                move.quantity if move.state == "done" else move.product_uom_qty
            )
            qty -= move.product_uom._compute_quantity(
                qty_to_compute,
                self.product_uom,
                rounding_method="HALF-UP",
                raise_if_failure=False,
            )
        return qty

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """Lệch nhóm ĐVT: giữ nguyên số, phiếu kho chạy theo ĐVT kho."""
        if self._context.get("skip_procurement"):
            return True
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        procurements = []
        for line in self:
            line = line.with_company(line.company_id)
            if (
                line.state != "sale"
                or line.order_id.locked
                or not line.product_id.type in ("consu", "product")
            ):
                continue
            qty = line._get_qty_procurement(previous_product_uom_qty)
            if (
                float_compare(
                    qty, line.product_uom_qty, precision_digits=precision
                )
                == 0
            ):
                continue
            group_id = line._get_procurement_group()
            if not group_id:
                group_id = self.env["procurement.group"].create(
                    line._prepare_procurement_group_vals()
                )
                line.order_id.procurement_group_id = group_id
            else:
                updated_vals = {}
                if group_id.partner_id != line.order_id.partner_shipping_id:
                    updated_vals.update(
                        {"partner_id": line.order_id.partner_shipping_id.id}
                    )
                if group_id.move_type != line.order_id.picking_policy:
                    updated_vals.update(
                        {"move_type": line.order_id.picking_policy}
                    )
                if updated_vals:
                    group_id.write(updated_vals)
            values = line._prepare_procurement_values(group_id=group_id)
            product_qty = line.product_uom_qty - qty
            line_uom = line.product_uom
            quant_uom = line.product_id.uom_id
            if line_uom.category_id == quant_uom.category_id:
                product_qty, procurement_uom = line_uom._adjust_uom_quantities(
                    product_qty, quant_uom
                )
            else:
                procurement_uom = quant_uom
            procurements.append(
                line._create_procurement(product_qty, procurement_uom, values)
            )
        if procurements:
            self.env["procurement.group"].run(procurements)
        orders = self.mapped("order_id")
        for order in orders:
            pickings_to_confirm = order.picking_ids.filtered(
                lambda p: p.state not in ["cancel", "done"]
            )
            if pickings_to_confirm:
                pickings_to_confirm.action_confirm()
        return True

    def _create_procurement(self, product_qty, procurement_uom, values):
        """Chứng từ gốc của phiếu kho lấy mã đơn hàng."""
        self.ensure_one()
        return self.env["procurement.group"].Procurement(
            self.product_id,
            product_qty,
            procurement_uom,
            self.order_id.partner_shipping_id.property_stock_customer,
            self.product_id.display_name,
            self.order_id.catering_reference or self.order_id.name,
            self.order_id.company_id,
            values,
        )

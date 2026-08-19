from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ClientContract(models.Model):
    _name = "set_top_menu.client.contract"
    _description = "Hợp đồng client"
    _order = "date_start desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Tên hợp đồng", required=True, index=True)
    contract_number = fields.Char(
        string="Số hợp đồng", required=True, copy=False, index=True
    )
    client_id = fields.Many2one(
        "res.partner",
        string="Client",
        required=True,
        index=True,
        ondelete="restrict",
        domain="[('customer_rank', '>', 0)]",
    )
    date_start = fields.Date(string="Ngày bắt đầu", required=True, default=fields.Date.context_today)
    date_end = fields.Date(string="Ngày kết thúc")
    amount = fields.Monetary(
        string="Giá trị hợp đồng",
        currency_field="currency_id",
        compute="_compute_amount",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    status = fields.Selection(
        [
            ("draft", "Dự thảo"),
            ("active", "Đang hiệu lực"),
            ("expired", "Hết hạn"),
            ("cancelled", "Đã huỷ"),
        ],
        string="Trạng thái",
        required=True,
        default="draft",
        index=True,
    )
    notes = fields.Text(string="Ghi chú")
    company_id = fields.Many2one(
        "res.company", string="Công ty", required=True, default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)
    task_ids = fields.One2many(
        "set_top_menu.client.contract.task",
        "contract_id",
        string="Hợp đồng Chi tiết",
        copy=True,
    )

    _sql_constraints = [
        (
            "contract_number_company_unique",
            "unique(contract_number, company_id)",
            "Số hợp đồng đã tồn tại trong công ty này.",
        ),
    ]

    @api.constrains("date_start", "date_end")
    def _check_contract_dates(self):
        for contract in self:
            if contract.date_end and contract.date_end < contract.date_start:
                raise ValidationError("Ngày kết thúc không được trước ngày bắt đầu.")

    @api.depends("task_ids.subtotal")
    def _compute_amount(self):
        for contract in self:
            contract.amount = sum(contract.task_ids.mapped("subtotal"))


class ClientContractTask(models.Model):
    _name = "set_top_menu.client.contract.task"
    _description = "Task chi tiết hợp đồng"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    contract_id = fields.Many2one(
        "set_top_menu.client.contract",
        string="Hợp đồng",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm",
        required=True,
        domain="[('sale_ok', '=', True)]",
    )
    name = fields.Text(string="Mô tả", required=True)
    quantity = fields.Float(string="Số lượng", required=True, default=1.0)
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Đơn vị",
        required=True,
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    product_uom_category_id = fields.Many2one(
        related="product_id.uom_id.category_id",
        depends=["product_id"],
    )
    price_unit = fields.Float(string="Đơn giá", required=True, digits="Product Price")
    subtotal = fields.Monetary(
        string="Thành tiền",
        currency_field="currency_id",
        compute="_compute_subtotal",
        store=True,
    )
    currency_id = fields.Many2one(related="contract_id.currency_id", store=True)

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for task in self:
            task.subtotal = task.quantity * task.price_unit

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.product_uom_id = self.product_id.uom_id
            self.price_unit = self.product_id.lst_price

    @api.constrains("quantity")
    def _check_quantity(self):
        for task in self:
            if task.quantity <= 0:
                raise ValidationError("Số lượng sản phẩm phải lớn hơn 0.")

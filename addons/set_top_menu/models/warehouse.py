from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.crall_material.models.hnck_client import HnckClient


class Warehouse(models.Model):
    _name = "set_top_menu.warehouse"
    _description = "Kho"
    _order = "name"

    name = fields.Char(string="Tên kho", required=True, index=True)
    code = fields.Char(
        string="Mã kho", required=True, copy=False, index=True
    )
    address = fields.Char(string="Địa chỉ", required=True)
    area = fields.Float(
        string="Diện tích (m²)",
        digits=(10, 2),
        help="Diện tích kho tính bằng mét vuông (m²).",
    )
    active = fields.Boolean(string="Đang hoạt động", default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "Mã kho không được trùng."),
    ]

    @api.constrains("area")
    def _check_area(self):
        for warehouse in self:
            if warehouse.area and warehouse.area < 0:
                raise ValidationError("Diện tích kho không được âm.")

    def action_open_create_popup(self):
        """Nút Thêm mới: mở form tạo kho trong dialog (popup)."""
        form_view = self.env.ref("set_top_menu.view_warehouse_form_create")
        return {
            "type": "ir.actions.act_window",
            "name": "Thêm kho mới",
            "res_model": "set_top_menu.warehouse",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "target": "new",
        }

    def action_push_supplier_warehouses(self):
        """Nút Đồng bộ: chỉ hiện khi tick chọn kho trên danh sách.

        Gửi các kho đang chọn lên API ``supplier/warehouses/merge`` (POST,
        ký X-Signature; token hết hạn thì tự lấy mới).
        """
        if not self:
            raise UserError(_("Vui lòng chọn ít nhất một kho để đồng bộ."))
        payloads = [
            {
                "ma_kho": (warehouse.code or "").upper(),
                "ten_kho": warehouse.name or "",
                "dia_chi": warehouse.address or "",
                "dien_tich": warehouse.area or 0.0,
            }
            for warehouse in self
        ]
        result = HnckClient(self.env).push_supplier_warehouses(payloads)
        message = _("Đã gửi %s kho lên API nhà cung cấp.") % len(payloads)
        if isinstance(result, dict) and result.get("message"):
            message = "%s %s" % (message, result["message"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đồng bộ kho"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

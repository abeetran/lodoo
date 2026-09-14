from odoo import _, fields, models
from odoo.exceptions import UserError

from .hnck_client import HnckClient


class CrallProductionSite(models.Model):
    _name = "crall.production.site"
    _description = "Crall Production Site"
    _order = "name"

    name = fields.Char(string="Tên cơ sở", required=True)
    code = fields.Char(string="Mã cơ sở", copy=False)
    address = fields.Char(string="Địa chỉ")
    phone = fields.Char(string="Điện thoại")
    tax_number = fields.Char(string="Mã số thuế")
    supplier_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp",
        domain=[("crall_sub_supplier_id", "!=", False)],
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")

    def action_sync_sites(self):
        if not self:
            raise UserError(_("Vui lòng chọn ít nhất một cơ sở sản xuất."))
        records = [
            {
                "ma_co_so": site.code or "",
                "ten_co_so": site.name or "",
                "dia_chi": site.address or "",
            }
            for site in self
        ]
        result = HnckClient(self.env).merge_facilities(records)
        message = _("Đã đẩy %s cơ sở sản xuất lên HNCK.") % len(records)
        if isinstance(result, dict) and result.get("message"):
            message = "%s %s" % (message, result["message"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Crall sync completed",
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

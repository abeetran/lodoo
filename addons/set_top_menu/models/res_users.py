from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.crall_material.models.hnck_client import HnckClient

# Tạo user tự động (SSO, đăng ký) được miễn kiểm tra mã NV/vai trò
# vì bổ sung sau khi đăng nhập lần đầu; form nhập tay vẫn bắt buộc.
SKIP_USER_CHECKS = "set_top_menu_skip_user_checks"


class ResUsers(models.Model):
    _inherit = "res.users"

    employee_code = fields.Char(
        string="Mã nhân viên",
        copy=False,
        index=True,
        help="Mã nhân viên của người dùng.",
    )
    job_position = fields.Char(string="Chức vụ")
    birth_date = fields.Date(string="Ngày sinh")
    identity_number = fields.Char(
        string="Số CCCD/Định danh",
        copy=False,
        index=True,
    )
    contact_phone = fields.Char(string="Số điện thoại")
    contact_address = fields.Char(string="Địa chỉ")
    business_owner = fields.Boolean(string="Chủ cơ sở/chủ NCC")
    business_processor = fields.Boolean(string="Sơ chế/Chế biến")
    business_transporter = fields.Boolean(string="Vận chuyển")
    transport_vehicle = fields.Char(string="Phương tiện vận chuyển")
    transport_plate = fields.Char(string="Biển số xe")
    health_cert_number = fields.Char(string="Số giấy khám sức khỏe")
    health_cert_place = fields.Char(string="Nơi khám")
    health_cert_date = fields.Date(string="Ngày khám")
    health_cert_expiry = fields.Date(string="Ngày hết hạn")
    food_safety_cert_number = fields.Char(string="Số GCN tập huấn")
    food_safety_issue_date = fields.Date(string="Ngày cấp")
    food_safety_issuer = fields.Char(string="Đơn vị cấp")

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(SKIP_USER_CHECKS):
            return super().create(vals_list)
        users = super().create(vals_list)
        no_code = users.filtered(lambda user: not user.employee_code)
        if no_code:
            raise ValidationError("Vui lòng nhập Mã nhân viên.")
        no_role = users.filtered(
            lambda user: not user.share
            and not (
                user.business_owner
                or user.business_processor
                or user.business_transporter
            )
        )
        if no_role:
            raise ValidationError(
                "Vui lòng chọn ít nhất một vai trò ở tab Nghiệp vụ: "
                "Chủ cơ sở/chủ NCC, Sơ chế/Chế biến hoặc Vận chuyển."
            )
        return users

    @api.model
    def _signup_create_user(self, values):
        self = self.with_context(**{SKIP_USER_CHECKS: True})
        return super()._signup_create_user(values)

    @api.constrains(
        "business_owner", "business_processor", "business_transporter"
    )
    def _check_business_role(self):
        missing = self.filtered(
            lambda user: not (
                user.business_owner
                or user.business_processor
                or user.business_transporter
            )
        )
        if missing:
            raise ValidationError(
                "Vui lòng chọn ít nhất một vai trò ở tab Nghiệp vụ: "
                "Chủ cơ sở/chủ NCC, Sơ chế/Chế biến hoặc Vận chuyển."
            )

    @api.constrains("employee_code")
    def _check_employee_code(self):
        if self.filtered(lambda user: not user.employee_code):
            raise ValidationError("Vui lòng nhập Mã nhân viên.")

    @api.constrains("business_transporter", "transport_plate")
    def _check_transport_plate(self):
        missing = self.filtered(
            lambda user: user.business_transporter
            and not user.transport_plate
        )
        if missing:
            raise ValidationError(
                "Vui lòng nhập Biển số xe khi chọn vai trò Vận chuyển."
            )

    @api.constrains(
        "business_processor",
        "health_cert_number",
        "health_cert_date",
        "health_cert_expiry",
        "food_safety_cert_number",
        "food_safety_issue_date",
    )
    def _check_processor_certificates(self):
        for user in self.filtered("business_processor"):
            missing = []
            if not user.health_cert_number:
                missing.append("Số giấy khám sức khỏe")
            if not user.health_cert_date:
                missing.append("Ngày khám")
            if not user.health_cert_expiry:
                missing.append("Ngày hết hạn")
            if not user.food_safety_cert_number:
                missing.append("Số GCN tập huấn")
            if not user.food_safety_issue_date:
                missing.append("Ngày cấp")
            if missing:
                raise ValidationError(
                    "Vai trò Sơ chế/Chế biến còn thiếu: %s."
                    % ", ".join(missing)
                )

    def action_push_supplier_users(self):
        """Nút Đồng bộ: chỉ hiện khi tick chọn người dùng trên danh sách.

        Gửi các người dùng đang chọn lên API ``supplier/users/merge``
        (POST, ký X-Signature; token hết hạn thì tự lấy mới).
        """
        if not self:
            raise UserError(_("Vui lòng chọn ít nhất một người dùng để đồng bộ."))
        payloads = [user._supplier_user_push_payload() for user in self]
        result = HnckClient(self.env).push_supplier_users(payloads)
        message = _("Đã gửi %s người dùng lên API nhà cung cấp.") % len(payloads)
        if isinstance(result, dict) and result.get("message"):
            message = "%s %s" % (message, result["message"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đồng bộ người dùng"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def _supplier_user_push_payload(self):
        """Serialize one user into the supplier merge body format."""
        self.ensure_one()

        def _date(value):
            return fields.Date.to_string(value) if value else ""

        payload = {
            "ma_nhan_su": (self.employee_code or "").upper(),
            "ho_ten": self.name or "",
            "vi_tri": self.job_position or "",
            "dien_thoai": self.contact_phone or "",
            "la_chu_co_so": bool(self.business_owner),
            "la_nguoi_che_bien": bool(self.business_processor),
            "la_nguoi_giao_hang": bool(self.business_transporter),
            "trang_thai": bool(self.active),
        }
        if self.business_transporter:
            payload["phuong_tien"] = self.transport_vehicle or ""
            payload["bien_so"] = self.transport_plate or ""
        if self.business_processor:
            payload["giay_kham_suc_khoe"] = {
                "so_giay": self.health_cert_number or "",
                "ngay_kham": _date(self.health_cert_date),
                "ngay_het_han": _date(self.health_cert_expiry),
                "noi_kham": self.health_cert_place or "",
            }
            payload["chung_nhan_tap_huan_attp"] = {
                "so_gcn": self.food_safety_cert_number or "",
                "ngay_cap": _date(self.food_safety_issue_date),
                "don_vi_cap": self.food_safety_issuer or "",
            }
        return payload

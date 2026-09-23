from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    crall_supplier_api_url = fields.Char(
        string="Supplier API URL",
        config_parameter="crall_material.supplier_api_url",
        default="https://ncc-api.hanoicheck.com.vn/supplier/standard-foods",
    )
    crall_supplier_api_token = fields.Char(
        string="Supplier API token",
        config_parameter="crall_material.supplier_api_token",
        password=True,
    )
    crall_supplier_api_referer = fields.Char(
        string="Supplier API referer",
        config_parameter="crall_material.supplier_api_referer",
        default="https://ncc.hanoicheck.com.vn",
    )
    crall_school_api_url = fields.Char(
        string="School API URL",
        config_parameter="crall_material.school_api_url",
        default="https://ncc-api.hanoicheck.com.vn/supplier/schools/paginate?page=1&per_page=30",
    )
    crall_food_api_url = fields.Char(
        string="Food API URL",
        config_parameter="crall_material.food_api_url",
        default="https://ncc-api.hanoicheck.com.vn/supplier/foods/paginate?page=1&page_size=15",
    )
    crall_sub_supplier_api_url = fields.Char(
        string="Sub-supplier API URL",
        config_parameter="crall_material.sub_supplier_api_url",
        default="https://ncc-api.hanoicheck.com.vn/supplier/sub-suppliers/paginate?page=1&per_page=15",
    )
    crall_supplier_dish_merge_url = fields.Char(
        string="Supplier dish merge URL (trống = dùng HNCK base + supplier/dishes/merge)",
        config_parameter="crall_material.supplier_dish_merge_url",
    )
    crall_hnck_api_base = fields.Char(
        string="HNCK API base URL (.env HNCK_API_URL)",
        config_parameter="crall_material.hnck_api_base",
        default="https://ncc-api.hanoicheck.com.vn/api/",
    )
    crall_hnck_grant_type = fields.Char(
        string="HNCK grant type (.env GRANT_TYPE)",
        config_parameter="crall_material.hnck_grant_type",
        default="client_credentials",
    )
    crall_hnck_client_id = fields.Char(
        string="HNCK client ID (.env CLIENT_ID)",
        config_parameter="crall_material.hnck_client_id",
    )
    crall_hnck_client_secret = fields.Char(
        string="HNCK client secret (.env CLIENT_SECRET)",
        config_parameter="crall_material.hnck_client_secret",
        password=True,
    )
    crall_hnck_hmac_secret = fields.Char(
        string="HNCK HMAC secret (.env HMAC_SECRET)",
        config_parameter="crall_material.hnck_hmac_secret",
        password=True,
    )

    def action_sync_crall_materials(self):
        self.ensure_one()
        self.set_values()
        self.env["product.template"].sync_crall_materials(
            url=self.crall_supplier_api_url,
            token=self.crall_supplier_api_token,
            referer=self.crall_supplier_api_referer,
        )
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_sync_crall_sub_suppliers(self):
        self.ensure_one()
        self.set_values()
        self.env["res.partner"].sync_crall_sub_suppliers(
            url=self.crall_sub_supplier_api_url,
            token=self.crall_supplier_api_token,
            referer=self.crall_supplier_api_referer,
        )
        return {"type": "ir.actions.client", "tag": "reload"}
from odoo import fields, models
from odoo.tools.convert import str2bool


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Boolean fields intentionally do NOT use config_parameter shortcut.
    # Odoo's get_values() converts the stored string via bool(), and
    # bool("False") == True in Python — which would enable IP filtering
    # (and any other flag) unintentionally on every settings save.
    # We handle these manually in get_values / set_values instead.
    mcp_enabled = fields.Boolean(string="Enable MCP Server")
    mcp_rate_limit = fields.Integer(
        string="Rate Limit (req/min)",
        config_parameter="xf_mcp.rate_limit",
        default=60,
    )
    mcp_max_records = fields.Integer(
        string="Max Records Per Request",
        config_parameter="xf_mcp.max_records",
        default=200,
    )
    mcp_ip_filtering_enabled = fields.Boolean(string="Enable IP Filtering")
    mcp_ip_filtering_strategy = fields.Selection(
        selection=[
            ("allow_list", "Allow List (only listed IPs can connect)"),
            ("deny_list", "Deny List (block listed IPs)"),
        ],
        string="IP Filtering Strategy",
        config_parameter="xf_mcp.ip_filtering_strategy",
        default="allow_list",
    )
    # Text fields cannot use config_parameter shortcut — handled via get/set_values
    mcp_ip_list = fields.Text(
        string="IP List",
        help="One entry per line: IP address (192.168.1.100) or CIDR mask (192.168.1.0/24)",
    )
    mcp_sse_enabled = fields.Boolean(string="Enable SSE Transport")
    mcp_logging_enabled = fields.Boolean(string="Enable Audit Logging")
    mcp_log_retention_days = fields.Integer(
        string="Log Retention (days)",
        config_parameter="xf_mcp.log_retention_days",
        default=90,
    )
    mcp_session_ttl_hours = fields.Integer(
        string="Session TTL (hours)",
        config_parameter="xf_mcp.session_ttl_hours",
        default=24,
    )
    mcp_allowed_origins = fields.Char(
        string="Allowed Origins",
        config_parameter="xf_mcp.allowed_origins",
        help="Comma-separated allowed CORS origins. Empty = reject unknown origins.",
    )
    # Text field — handled via get/set_values
    mcp_system_instructions = fields.Text(
        string="System Instructions",
        help="Instructions sent to AI agents on initialize and via odoo://system/prompt resource.",
    )

    def get_values(self):
        res = super().get_values()
        get_param = self.env["ir.config_parameter"].sudo().get_param
        # Boolean params: compare explicitly against "True"/"1" because
        # bool("False") == True in Python — the config_parameter shortcut is unsafe for booleans.
        res["mcp_enabled"] = str2bool(get_param("xf_mcp.enabled", "False"))
        res["mcp_sse_enabled"] = str2bool(get_param("xf_mcp.sse_enabled", "True"))
        res["mcp_ip_filtering_enabled"] = str2bool(get_param("xf_mcp.ip_filtering_enabled", "False"))
        res["mcp_logging_enabled"] = str2bool(get_param("xf_mcp.logging_enabled", "True"))
        # Text params (not supported by config_parameter shortcut)
        res["mcp_ip_list"] = get_param("xf_mcp.ip_list", "")
        res["mcp_system_instructions"] = get_param("xf_mcp.system_instructions", "")
        return res

    def set_values(self):
        res = super().set_values()
        set_param = self.env["ir.config_parameter"].sudo().set_param
        set_param("xf_mcp.enabled", str(self.mcp_enabled))
        set_param("xf_mcp.sse_enabled", str(self.mcp_sse_enabled))
        set_param("xf_mcp.ip_filtering_enabled", str(self.mcp_ip_filtering_enabled))
        set_param("xf_mcp.logging_enabled", str(self.mcp_logging_enabled))
        set_param("xf_mcp.ip_list", self.mcp_ip_list or "")
        set_param("xf_mcp.system_instructions", self.mcp_system_instructions or "")
        return res

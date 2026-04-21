from datetime import timedelta

from odoo import api, fields, models


class McpAuditLog(models.Model):
    _name = "mcp.audit.log"
    _description = "MCP Audit Log"
    _order = "timestamp desc"

    session_id = fields.Many2one(
        comodel_name="mcp.session",
        string="Session",
        readonly=True,
        index=True,
        ondelete="set null",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
        readonly=True,
        index=True,
    )
    method = fields.Char(
        string="MCP Method",
        readonly=True,
        index=True,
        help="e.g., tools/call, resources/read, prompts/get",
    )
    tool_name = fields.Char(string="Tool", readonly=True)
    resource_uri = fields.Char(string="Resource URI", readonly=True)
    prompt_name = fields.Char(string="Prompt", readonly=True)
    request_data = fields.Text(
        string="Request Data",
        readonly=True,
        help="Sanitized request parameters (truncated)",
    )
    response_status = fields.Selection(
        selection=[
            ("success", "Success"),
            ("error", "Error"),
            ("denied", "Denied"),
        ],
        string="Status",
        readonly=True,
        index=True,
    )
    error_message = fields.Text(string="Error", readonly=True)
    ip_address = fields.Char(string="IP Address", readonly=True, index=True)
    user_agent = fields.Char(string="User Agent", readonly=True)
    duration_ms = fields.Float(string="Duration (ms)", readonly=True)
    timestamp = fields.Datetime(
        string="Timestamp",
        default=fields.Datetime.now,
        readonly=True,
        index=True,
    )

    @api.model
    def log_request(self, vals):
        """Create an audit log entry, truncating large fields."""
        if vals.get("request_data") and len(vals["request_data"]) > 5000:
            vals["request_data"] = vals["request_data"][:5000] + "... (truncated)"
        if vals.get("user_agent") and len(vals["user_agent"]) > 500:
            vals["user_agent"] = vals["user_agent"][:500]
        return self.sudo().create(vals)

    @api.model
    def cron_cleanup_old_logs(self):
        """Delete audit logs older than retention period."""
        days = int(self.env["ir.config_parameter"].sudo().get_param("xf_mcp.log_retention_days", "90"))
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.sudo().search([("timestamp", "<", cutoff)])
        count = len(old_logs)
        old_logs.unlink()
        return count

import secrets
from datetime import timedelta

from odoo import api, fields, models


class McpSession(models.Model):
    _name = "mcp.session"
    _description = "MCP Session"
    _order = "last_activity desc"

    session_id = fields.Char(
        string="Session ID",
        required=True,
        index=True,
        readonly=True,
        copy=False,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
        required=True,
        index=True,
        readonly=True,
        ondelete="cascade",
    )
    protocol_version = fields.Char(
        string="Protocol Version",
        readonly=True,
    )
    client_info = fields.Text(
        string="Client Info",
        readonly=True,
        help="JSON: client name, version, etc.",
    )
    last_activity = fields.Datetime(
        string="Last Activity",
        default=fields.Datetime.now,
        readonly=True,
        copy=False,
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )

    @api.model
    def create_session(self, user_id, protocol_version, client_info=None):
        """Create a new MCP session with a cryptographically random ID."""
        session_id = secrets.token_urlsafe(32)
        return self.sudo().create(
            {
                "session_id": session_id,
                "user_id": user_id,
                "protocol_version": protocol_version,
                "client_info": client_info,
            }
        )

    def touch(self):
        """Update last_activity timestamp.

        Plain UPDATE without ORM or any row-level lock.  The ORM's write()
        batch format can trigger serialization failures under concurrent load;
        acquiring FOR UPDATE here would also conflict with the FOR KEY SHARE
        lock PostgreSQL takes when inserting a referencing mcp_audit_log row.
        Missing a touch on a busy session is harmless — TTL is in hours.
        """
        self.env.cr.execute(
            "UPDATE mcp_session SET last_activity = (NOW() AT TIME ZONE 'UTC') WHERE id = %s",
            [self.id],
        )

    @api.model
    def find_session(self, session_id):
        """Find an active session by its ID."""
        return self.sudo().search(
            [
                ("session_id", "=", session_id),
                ("active", "=", True),
            ],
            limit=1,
        )

    @api.model
    def cleanup_expired(self, ttl_hours=24):
        """Deactivate sessions older than TTL."""
        cutoff = fields.Datetime.now() - timedelta(hours=ttl_hours)
        expired = self.sudo().search(
            [
                ("last_activity", "<", cutoff),
                ("active", "=", True),
            ]
        )
        expired.write({"active": False})
        return len(expired)

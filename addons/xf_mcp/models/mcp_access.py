import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class McpAccess(models.Model):
    _name = "mcp.access"
    _description = "MCP Model Access Override"
    _order = "model_name"

    name = fields.Char(
        string="Name",
        compute="_compute_name",
        store=True,
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
        index=True,
    )
    model_name = fields.Char(
        string="Model Name",
        related="model_id.model",
        store=True,
        index=True,
    )
    read_access = fields.Boolean(string="Read", default=True)
    write_access = fields.Boolean(string="Write", default=True)
    create_access = fields.Boolean(string="Create", default=True)
    delete_access = fields.Boolean(string="Delete", default=True)
    method_call_access = fields.Boolean(string="Method Call", default=True)
    allowed_fields = fields.Text(
        string="Allowed Fields",
        help="JSON list of allowed field names. Empty = all accessible fields.",
    )
    blocked_methods = fields.Text(
        string="Blocked Methods",
        help="JSON list of additionally blocked method names.",
    )
    group_ids = fields.Many2many(
        comodel_name="res.groups",
        string="Restrict to Groups",
        help="Only users in these groups can access this model via MCP. Empty = all MCP users.",
    )
    active = fields.Boolean(string="Active", default=True)
    description = fields.Text(string="Notes")

    # _model_id_unique = models.Constraint(
    #     "unique(model_id)",
    #     "Only one MCP access override per model!",
    # )
    _sql_constraints = [
        (
            'model_id_unique',
            'unique(model_id)',
            'Only one MCP access override per model!'
        )
    ]

    @api.depends("model_id")
    def _compute_name(self):
        for record in self:
            record.name = f"MCP: {record.model_name}" if record.model_name else ""

    @api.constrains("model_id")
    def _check_blocked_model(self):
        for record in self:
            if record.model_name in self.env["mcp.tool"]._blocked_models:
                raise ValidationError(
                    self.env._(
                        "Model '%(model)s' cannot be configured — it is always blocked from MCP.",
                        model=record.model_name,
                    )
                )

    @api.constrains("allowed_fields")
    def _check_allowed_fields(self):
        for record in self:
            if record.allowed_fields:
                try:
                    val = json.loads(record.allowed_fields)
                    if not isinstance(val, list):
                        raise ValidationError(self.env._("Allowed fields must be a JSON list."))
                except (json.JSONDecodeError, TypeError) as e:
                    raise ValidationError(self.env._("Allowed fields must be valid JSON: %(error)s", error=e)) from e

    @api.constrains("blocked_methods")
    def _check_blocked_methods(self):
        for record in self:
            if record.blocked_methods:
                try:
                    val = json.loads(record.blocked_methods)
                    if not isinstance(val, list):
                        raise ValidationError(self.env._("Blocked methods must be a JSON list."))
                except (json.JSONDecodeError, TypeError) as e:
                    raise ValidationError(self.env._("Blocked methods must be valid JSON: %(error)s", error=e)) from e

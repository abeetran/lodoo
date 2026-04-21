import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class McpPrompt(models.Model):
    _name = "mcp.prompt"
    _description = "MCP Prompt"
    _order = "sequence, name"

    name = fields.Char(
        string="Name",
        required=True,
        index=True,
        help="Unique prompt identifier (slash command name)",
    )
    title = fields.Char(
        string="Title",
        help="Human-readable display name",
    )
    description = fields.Text(
        string="Description",
        help="Description for AI clients",
    )
    is_global = fields.Boolean(
        string="Global",
        default=True,
        help="Global prompts are visible to all MCP users. Personal prompts are user-specific.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Owner",
        help="Owner of personal prompt (empty for global prompts)",
    )
    argument_ids = fields.One2many(
        comodel_name="mcp.prompt.argument",
        inverse_name="prompt_id",
        string="Arguments",
    )
    message_template = fields.Text(
        string="Message Template",
        required=True,
        help="Template text with {argument_name} placeholders for substitution",
    )
    role = fields.Selection(
        selection=[
            ("user", "User"),
            ("assistant", "Assistant"),
        ],
        string="Message Role",
        default="user",
    )
    active = fields.Boolean(string="Active", default=True)
    sequence = fields.Integer(string="Sequence", default=10)

    def init(self):
        """Create partial unique indexes for prompt name uniqueness."""
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS mcp_prompt_name_global_uniq
            ON mcp_prompt (name) WHERE is_global = True;
        """)
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS mcp_prompt_name_user_uniq
            ON mcp_prompt (name, user_id) WHERE is_global = False;
        """)

    @api.constrains("name", "is_global", "user_id")
    def _check_name_conflicts(self):
        for record in self:
            if not record.is_global:
                # User prompt name must not conflict with global prompts
                conflict = self.sudo().search(
                    [
                        ("name", "=", record.name),
                        ("is_global", "=", True),
                        ("id", "!=", record.id),
                    ],
                    limit=1,
                )
                if conflict:
                    raise ValidationError(
                        self.env._("Prompt name '%(name)s' conflicts with a global prompt.", name=record.name)
                    )

    @api.constrains("is_global", "user_id")
    def _check_user_id(self):
        for record in self:
            if not record.is_global and not record.user_id:
                raise ValidationError(self.env._("Personal prompts must have an owner."))
            if record.is_global and record.user_id:
                raise ValidationError(self.env._("Global prompts must not have an owner."))

    def to_mcp_prompt(self):
        """Convert to MCP prompts/list format."""
        self.ensure_one()
        result = {
            "name": self.name,
        }
        if self.title:
            result["title"] = self.title
        if self.description:
            result["description"] = self.description
        if self.argument_ids:
            result["arguments"] = [arg.to_mcp_argument() for arg in self.argument_ids]
        return result

    def render(self, arguments=None):
        """Render prompt template with provided arguments."""
        self.ensure_one()
        arguments = arguments or {}

        # Validate required arguments
        for arg in self.argument_ids:
            if arg.required and arg.name not in arguments:
                raise ValidationError(self.env._("Required argument '%(arg)s' is missing.", arg=arg.name))

        try:

            def _replace(match):
                key = match.group(1)
                if key not in arguments:
                    raise KeyError(key)
                return str(arguments[key])

            text = re.sub(r"\{(\w+)\}", _replace, self.message_template)
        except KeyError as e:
            raise ValidationError(self.env._("Unknown argument in template: %(arg)s", arg=e)) from e

        return {
            "description": self.description or "",
            "messages": [
                {
                    "role": self.role,
                    "content": {
                        "type": "text",
                        "text": text,
                    },
                }
            ],
        }


class McpPromptArgument(models.Model):
    _name = "mcp.prompt.argument"
    _description = "MCP Prompt Argument"
    _order = "sequence, name"

    prompt_id = fields.Many2one(
        comodel_name="mcp.prompt",
        string="Prompt",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(
        string="Name",
        required=True,
    )
    description = fields.Char(
        string="Description",
    )
    required = fields.Boolean(
        string="Required",
        default=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)

    def to_mcp_argument(self):
        """Convert to MCP argument format."""
        self.ensure_one()
        result = {"name": self.name}
        if self.description:
            result["description"] = self.description
        result["required"] = self.required
        return result

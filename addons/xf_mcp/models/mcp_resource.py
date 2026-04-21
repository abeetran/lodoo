import json
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.release import version as odoo_version

_logger = logging.getLogger(__name__)


class McpResource(models.Model):
    _name = "mcp.resource"
    _description = "MCP Resource"
    _order = "sequence, name"

    name = fields.Char(
        string="Name",
        required=True,
        help="Human-readable resource name",
    )
    description = fields.Text(
        string="Description",
        help="Description for AI clients",
    )
    uri_pattern = fields.Char(
        string="URI Pattern",
        required=True,
        help="Static URI or URI template with {param} placeholders",
    )
    is_template = fields.Boolean(
        string="Is Template",
        compute="_compute_is_template",
        store=True,
    )
    mime_type = fields.Char(
        string="MIME Type",
        default="application/json",
    )
    method_name = fields.Char(
        string="Method",
        required=True,
        help="Python method name on mcp.resource to resolve content",
    )
    active = fields.Boolean(string="Active", default=True)
    sequence = fields.Integer(string="Sequence", default=10)

    # _uri_pattern_unique = models.Constraint(
    #     "unique(uri_pattern)",
    #     "URI pattern must be unique!",
    # )
    _sql_constraints = [
        ('uri_pattern_unique', 'unique(uri_pattern)', 'URI pattern must be unique!')
    ]

    @api.depends("uri_pattern")
    def _compute_is_template(self):
        for record in self:
            record.is_template = bool(record.uri_pattern and "{" in record.uri_pattern)

    def to_mcp_resource(self):
        """Convert to MCP resources/list format (static resources only)."""
        self.ensure_one()
        result = {
            "uri": self.uri_pattern,
            "name": self.name,
        }
        if self.description:
            result["description"] = self.description
        if self.mime_type:
            result["mimeType"] = self.mime_type
        return result

    def to_mcp_template(self):
        """Convert to MCP resources/templates/list format."""
        self.ensure_one()
        result = {
            "uriTemplate": self.uri_pattern,
            "name": self.name,
        }
        if self.description:
            result["description"] = self.description
        if self.mime_type:
            result["mimeType"] = self.mime_type
        return result

    # -------------------------------------------------------------------------
    # URI matching
    # -------------------------------------------------------------------------

    def _match_uri(self, uri):
        """Try to match a URI against this resource's pattern. Returns params dict or None."""
        self.ensure_one()
        if not self.is_template:
            return {} if uri == self.uri_pattern else None

        # Escape the pattern for regex, then replace escaped {param} with named groups
        escaped = re.escape(self.uri_pattern)
        regex_pattern = re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[^/]+)", escaped)
        match = re.fullmatch(regex_pattern, uri)
        return match.groupdict() if match else None

    @api.model
    def resolve_uri(self, uri):
        """Find a resource matching the URI and return its content.

        Uses sudo for resource registry lookup, but passes the caller's env
        to resolver methods so Odoo ACL applies to data access.
        """
        caller_env = self.env
        resource_model = self.sudo()

        # Try static resources first (exact match)
        static = resource_model.search([("uri_pattern", "=", uri), ("active", "=", True)], limit=1)
        if static:
            return static._resolve(uri, {}, caller_env)

        # Try templates
        templates = resource_model.search([("is_template", "=", True), ("active", "=", True)])
        for template in templates:
            params = template._match_uri(uri)
            if params is not None:
                return template._resolve(uri, params, caller_env)

        return None

    def _resolve(self, uri, params, caller_env):
        """Call the resource's resolve method and return MCP-formatted content."""
        self.ensure_one()
        method = getattr(self, self.method_name, None)
        if method is None:
            raise UserError(self.env._("Resource method '%(method)s' not found.", method=self.method_name))

        # Pass caller's env (not sudo) so data access respects Odoo ACL
        result = method(uri, params, caller_env)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": result.get("mimeType", self.mime_type or "application/json"),
                    "text": result.get("text", ""),
                }
            ],
        }

    # -------------------------------------------------------------------------
    # Resource resolver methods
    # -------------------------------------------------------------------------

    def _resolve_system_info(self, _uri, _params, env):
        """odoo://system/info"""
        modules = env["ir.module.module"].sudo().search([("state", "=", "installed")])
        company = env.company

        return {
            "text": json.dumps(
                {
                    "odoo_version": odoo_version,
                    "database": env.cr.dbname,
                    "company": {
                        "id": company.id,
                        "name": company.name,
                    },
                    "installed_modules_count": len(modules),
                    "server_info": {
                        "mcp_module": "xf_mcp",
                        "mcp_version": "17.0.1.0.0",
                        "protocol_version": "2025-11-25",
                    },
                },
                indent=2,
            ),
        }

    def _resolve_system_prompt(self, _uri, _params, env):
        """odoo://system/prompt — returns configurable system instructions."""
        instructions = env["ir.config_parameter"].sudo().get_param("xf_mcp.system_instructions", "")
        default_instructions = (
            "You are connected to an Odoo ERP system via the MCP protocol.\n"
            "Use resources to discover models and schemas before calling tools.\n"
            "All operations run with your Odoo user permissions.\n"
            "For multi-company setups, pass context={'allowed_company_ids': [company_id]} "
            "on create/write/method_call operations."
        )
        return {
            "mimeType": "text/plain",
            "text": instructions or default_instructions,
        }

    def _resolve_user_me(self, _uri, _params, env):
        """odoo://user/me"""
        user = env.user
        return {
            "text": json.dumps(
                {
                    "id": user.id,
                    "login": user.login,
                    "name": user.name,
                    "email": user.email or "",
                    "lang": user.lang or "",
                    "tz": user.tz or "",
                    "company": {
                        "id": user.company_id.id,
                        "name": user.company_id.name,
                    },
                    "companies": [{"id": c.id, "name": c.name} for c in user.company_ids],
                    "groups": [g.full_name for g in user.group_ids],
                    "is_admin": user._is_admin(),
                    "is_mcp_admin": user.has_group("xf_mcp.group_mcp_admin"),
                },
                indent=2,
            ),
        }

    def _resolve_model_schema(self, _uri, params, env):
        """odoo://model/{model}/schema"""
        model_name = params.get("model")
        blocked = env["mcp.tool"]._blocked_models
        if not model_name or model_name in blocked:
            raise UserError(self.env._("Model '%(model)s' is not accessible.", model=model_name))
        if model_name not in env:
            raise UserError(self.env._("Model '%(model)s' does not exist.", model=model_name))

        model = env[model_name]
        fields_info = model.fields_get()

        schema = {}
        for fname, finfo in fields_info.items():
            schema[fname] = {
                "type": finfo.get("type"),
                "string": finfo.get("string"),
                "required": finfo.get("required", False),
                "readonly": finfo.get("readonly", False),
                "help": finfo.get("help", ""),
            }
            if finfo.get("relation"):
                schema[fname]["relation"] = finfo["relation"]
            if finfo.get("selection"):
                schema[fname]["selection"] = finfo["selection"]

        return {
            "text": json.dumps(
                {
                    "model": model_name,
                    "description": model._description or "",
                    "fields": schema,
                    "field_count": len(schema),
                },
                indent=2,
            ),
        }

    def _resolve_model_access(self, _uri, params, env):
        """odoo://model/{model}/access"""
        model_name = params.get("model")
        blocked = env["mcp.tool"]._blocked_models
        if not model_name or model_name in blocked:
            raise UserError(self.env._("Model '%(model)s' is not accessible.", model=model_name))
        if model_name not in env:
            raise UserError(self.env._("Model '%(model)s' does not exist.", model=model_name))

        # Check Odoo native ACL
        model_obj = env[model_name]
        perms = {
            "read": model_obj.check_access_rights("read", raise_exception=False),
            "write": model_obj.check_access_rights("write", raise_exception=False),
            "create": model_obj.check_access_rights("create", raise_exception=False),
            "unlink": model_obj.check_access_rights("unlink", raise_exception=False),
        }

        # Check MCP overrides
        mcp_access = (
            env["mcp.access"].sudo().with_context(active_test=False).search([("model_name", "=", model_name)], limit=1)
        )
        mcp_overrides = None
        if mcp_access:
            mcp_overrides = {
                "active": mcp_access.active,
                "read_access": mcp_access.read_access,
                "write_access": mcp_access.write_access,
                "create_access": mcp_access.create_access,
                "delete_access": mcp_access.delete_access,
                "method_call_access": mcp_access.method_call_access,
                "allowed_fields": json.loads(mcp_access.allowed_fields) if mcp_access.allowed_fields else [],
            }

        return {
            "text": json.dumps(
                {
                    "model": model_name,
                    "odoo_permissions": perms,
                    "mcp_overrides": mcp_overrides,
                    "effective": {
                        "read": perms["read"] and (not mcp_access or mcp_access.read_access),
                        "write": perms["write"] and (not mcp_access or mcp_access.write_access),
                        "create": perms["create"] and (not mcp_access or mcp_access.create_access),
                        "unlink": perms["unlink"] and (not mcp_access or mcp_access.delete_access),
                    },
                },
                indent=2,
            ),
        }

    def _resolve_module_info(self, _uri, params, env):
        """odoo://module/{module}/info"""
        module_name = params.get("module")
        if not module_name:
            raise UserError(self.env._("Parameter 'module' is required."))

        module = env["ir.module.module"].sudo().search([("name", "=", module_name)], limit=1)
        if not module:
            raise UserError(self.env._("Module '%(module)s' not found.", module=module_name))

        return {
            "text": json.dumps(
                {
                    "name": module.name,
                    "shortdesc": module.shortdesc or "",
                    "summary": module.summary or "",
                    "description": module.description or "",
                    "state": module.state,
                    "installed_version": module.installed_version or "",
                    "author": module.author or "",
                    "category": module.category_id.name if module.category_id else "",
                    "dependencies": [dep.name for dep in module.dependencies_id],
                },
                indent=2,
            ),
        }

    def _resolve_record(self, _uri, params, env):
        """odoo://record/{model}/{id}"""
        return self._resolve_record_impl(params, env, field_filter=None)

    def _resolve_record_fields(self, _uri, params, env):
        """odoo://record/{model}/{id}/fields/{fields} — field-limited record read."""
        field_filter = params.get("fields", "")
        return self._resolve_record_impl(params, env, field_filter=field_filter)

    def _resolve_record_impl(self, params, env, field_filter=None):
        """Shared implementation for record resolvers."""
        model_name = params.get("model")
        record_id = params.get("id")
        blocked = env["mcp.tool"]._blocked_models
        if not model_name or model_name in blocked:
            raise UserError(self.env._("Model '%(model)s' is not accessible.", model=model_name))
        if model_name not in env:
            raise UserError(self.env._("Model '%(model)s' does not exist.", model=model_name))

        try:
            record_id = int(record_id)
        except (TypeError, ValueError) as e:
            raise UserError(self.env._("Invalid record ID: %(id)s", id=record_id)) from e

        record = env[model_name].browse(record_id).exists()
        if not record:
            raise UserError(self.env._("Record %(model)s/%(id)s not found.", model=model_name, id=record_id))

        # Check mcp.access override
        mcp_access = (
            env["mcp.access"].sudo().with_context(active_test=False).search([("model_name", "=", model_name)], limit=1)
        )
        if mcp_access and not mcp_access.active:
            raise UserError(self.env._("MCP access to model '%(model)s' is disabled.", model=model_name))
        if mcp_access and not mcp_access.read_access:
            raise UserError(self.env._("Read access to model '%(model)s' is not allowed via MCP.", model=model_name))

        # Determine field list: URI-provided filter > mcp.access allowed_fields > accessible fields
        if field_filter:
            field_names = [f.strip() for f in field_filter.split(",") if f.strip()]
        else:
            # fields_get() returns only user-accessible fields, avoiding internal/broken ones
            field_names = list(record.fields_get(attributes=["type"]).keys())
            if mcp_access and mcp_access.allowed_fields:
                try:
                    allowed = set(json.loads(mcp_access.allowed_fields))
                    if allowed:
                        field_names = [f for f in field_names if f in allowed]
                except (json.JSONDecodeError, TypeError):  # pylint: disable=except-pass
                    pass

        # _format_records lives on mcp.tool; call on that model's instance
        # (method does not use self — it only processes the passed records arg)
        tool_model = env["mcp.tool"]
        data = tool_model._format_records(record, field_names)

        return {
            "text": json.dumps(
                {
                    "model": model_name,
                    "id": record_id,
                    "data": data[0] if data else {},
                },
                indent=2,
                default=str,
            ),
        }

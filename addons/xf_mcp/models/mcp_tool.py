import json
import logging
from datetime import timezone

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)
UTC = timezone.utc

_BLOCKED_KWARGS = frozenset({"env", "cr", "uid"})


class McpTool(models.Model):
    _name = "mcp.tool"
    _description = "MCP Tool"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True)
    title = fields.Char()
    description = fields.Text(required=True)
    input_schema = fields.Text(required=True)
    output_schema = fields.Text()
    method_name = fields.Char(required=True)
    category = fields.Selection(
        [("crud", "CRUD"), ("discovery", "Discovery"), ("custom", "Custom")],
        default="custom",
    )
    annotations = fields.Text()
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        ("name_unique", "unique(name)", "Tool name must be unique!"),
    ]

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("input_schema")
    def _check_input_schema(self):
        for record in self:
            try:
                schema = json.loads(record.input_schema)
                if schema.get("type") != "object":
                    raise ValidationError("Input schema 'type' must be 'object'.")
            except Exception as e:
                raise ValidationError(f"Invalid JSON schema: {e}")

    @api.constrains("annotations")
    def _check_annotations(self):
        for record in self:
            if record.annotations:
                try:
                    json.loads(record.annotations)
                except Exception as e:
                    raise ValidationError(f"Annotations must be valid JSON: {e}")

    @api.constrains("method_name")
    def _check_method_exists(self):
        for rec in self:
            if rec.method_name and not hasattr(self, rec.method_name):
                raise ValidationError(
                    f"Method '{rec.method_name}' does not exist on mcp.tool"
                )

    # -------------------------------------------------------------------------
    # EXECUTION ENTRYPOINT
    # -------------------------------------------------------------------------

    def execute(self, arguments=None):
        """Main dispatcher"""
        self.ensure_one()

        method = getattr(self, self.method_name, None)
        if not method:
            raise UserError(f"Method {self.method_name} not found")

        return method(self.env, arguments or {})

    # -------------------------------------------------------------------------
    # CRUD METHODS
    # -------------------------------------------------------------------------

    def _execute_search(self, env, args):
        model = args.get("model")
        domain = args.get("domain", [])
        fields_list = args.get("fields", [])
        limit = args.get("limit", 10)
        offset = args.get("offset", 0)
        order = args.get("order")

        if not model:
            raise UserError("Missing model")

        records = env[model].search(domain, limit=limit, offset=offset, order=order)

        return records.read(fields_list) if fields_list else records.read()

    def _execute_read(self, env, args):
        model = args.get("model")
        ids = args.get("ids", [])
        fields_list = args.get("fields", [])

        if not model or not ids:
            raise UserError("Missing model or ids")

        return env[model].browse(ids).read(fields_list)

    def _execute_create(self, env, args):
        model = args.get("model")
        if not model:
            raise UserError("Missing model")

        Model = env[model]

        if args.get("values_list"):
            vals_list = args["values_list"]
            records = Model.create(vals_list)
        else:
            values = args.get("values", {})
            records = Model.create(values)

        return {"ids": records.ids}

    def _execute_write(self, env, args):
        model = args.get("model")
        ids = args.get("ids")
        values = args.get("values")

        if not model or not ids or not values:
            raise UserError("Missing model, ids or values")

        env[model].browse(ids).write(values)
        return True

    def _execute_unlink(self, env, args):
        model = args.get("model")
        ids = args.get("ids")

        if not model or not ids:
            raise UserError("Missing model or ids")

        env[model].browse(ids).unlink()
        return True

    def _execute_count(self, env, args):
        model = args.get("model")
        domain = args.get("domain", [])

        if not model:
            raise UserError("Missing model")

        return env[model].search_count(domain)

    def _execute_read_group(self, env, args):
        model = args.get("model")
        groupby = args.get("groupby")
        fields_list = args.get("fields", [])
        domain = args.get("domain", [])

        if not model or not groupby:
            raise UserError("Missing model or groupby")

        return env[model].read_group(domain, fields_list, groupby)

    # -------------------------------------------------------------------------
    # DISCOVERY METHODS
    # -------------------------------------------------------------------------

    def _execute_default_get(self, env, args):
        model = args.get("model")
        fields_list = args.get("fields", [])

        if not model:
            raise UserError("Missing model")

        return env[model].default_get(fields_list)

    def _execute_list_modules(self, env, args):
        keyword = args.get("keyword")
        state = args.get("state", "installed")

        domain = [("state", "=", state)]
        if keyword:
            domain.append(("name", "ilike", keyword))

        modules = env["ir.module.module"].search(domain)
        return modules.read(["name", "state"])

    def _execute_list_companies(self, env, args):
        companies = env["res.company"].search([])
        return companies.read(["id", "name"])

    def _execute_method_call(self, env, arguments):
        model_name = arguments.get("model")
        method_name = arguments.get("method")

        if not model_name or not method_name:
            raise UserError("Missing model or method")

        model = env[model_name]

        ids = arguments.get("ids", [])
        args = arguments.get("args", [])
        kwargs = arguments.get("kwargs", {})

        records = model.browse(ids) if ids else model

        method = getattr(records, method_name, None)
        if not method:
            raise UserError(f"Method {method_name} not found")

        safe_kwargs = {k: v for k, v in kwargs.items() if k not in _BLOCKED_KWARGS}

        _logger.info(
            "MCP CALL model=%s method=%s ids=%s args=%s kwargs=%s",
            model_name, method_name, ids, args, safe_kwargs
        )

        result = method(*args, **safe_kwargs)

        return self._serialize_method_result(result)

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def _serialize_method_result(self, value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return {"result": value}
        if isinstance(value, dict):
            return {"result": value}
        if isinstance(value, (list, tuple)):
            return {"result": list(value)}
        if hasattr(value, "_name") and hasattr(value, "ids"):
            return {"result": {"model": value._name, "ids": value.ids}}
        return {"result": str(value)}
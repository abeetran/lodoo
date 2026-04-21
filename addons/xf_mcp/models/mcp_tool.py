import json
import logging
from datetime import datetime, timezone

from odoo import api, fields, models
from odoo.exceptions import MissingError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# Define UTC (Python 3.10 compatible)
UTC = timezone.utc

# Keys that must never be passed through to Odoo method kwargs
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

    # ✅ FIX: correct constraint
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
                raise ValidationError(f"Method '{rec.method_name}' does not exist on mcp.tool")

    # -------------------------------------------------------------------------
    # TIMEZONE FIX (IMPORTANT)
    # -------------------------------------------------------------------------

    def _localize_datetime_values(self, model, values, env):
        """Convert datetime string from user TZ → UTC (Odoo-safe)."""
        tz_name = env.context.get("tz") or env.user.tz
        if not tz_name:
            return values

        result = dict(values)

        for fname, value in values.items():
            if fname not in model._fields:
                continue
            if model._fields[fname].type != "datetime":
                continue
            if not isinstance(value, str) or not value:
                continue

            try:
                dt = fields.Datetime.from_string(value)

                # convert local → UTC properly
                localized = fields.Datetime.context_timestamp(
                    self.with_context(tz=tz_name),
                    dt,
                )

                result[fname] = fields.Datetime.to_string(localized)

            except Exception:
                pass

        return result

    # -------------------------------------------------------------------------
    # Example execution method (kept minimal)
    # -------------------------------------------------------------------------

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

        # ✅ Logging for debug
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
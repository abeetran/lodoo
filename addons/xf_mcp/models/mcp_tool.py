import json
import logging
from datetime import UTC, datetime

from odoo import api, fields, models
from odoo.exceptions import MissingError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# Keys that must never be passed through to Odoo method kwargs
_BLOCKED_KWARGS = frozenset({"env", "cr", "uid"})


class McpTool(models.Model):
    _name = "mcp.tool"
    _description = "MCP Tool"
    _order = "sequence, name"

    name = fields.Char(
        string="Name",
        required=True,
        index=True,
        help="Unique tool identifier (e.g., search, read, create)",
    )
    title = fields.Char(
        string="Title",
        help="Human-readable display name",
    )
    description = fields.Text(
        string="Description",
        required=True,
        help="Description for LLM understanding of when and how to use this tool",
    )
    input_schema = fields.Text(
        string="Input Schema",
        required=True,
        help="JSON Schema for tool parameters",
    )
    output_schema = fields.Text(
        string="Output Schema",
        help="JSON Schema for structured output (optional)",
    )
    method_name = fields.Char(
        string="Method",
        required=True,
        help="Python method name on mcp.tool to execute (e.g., _execute_search)",
    )
    category = fields.Selection(
        selection=[
            ("crud", "CRUD"),
            ("discovery", "Discovery"),
            ("custom", "Custom"),
        ],
        string="Category",
        default="custom",
    )
    annotations = fields.Text(
        string="Annotations",
        help="JSON: readOnlyHint, destructiveHint, idempotentHint, openWorldHint",
    )
    active = fields.Boolean(string="Active", default=True)
    sequence = fields.Integer(string="Sequence", default=10)

    _name_unique = models.Constraint(
        "unique(name)",
        "Tool name must be unique!",
    )

    # -------------------------------------------------------------------------
    # Extensible security constants (override in bridge modules via super())
    # -------------------------------------------------------------------------

    @property
    def _blocked_models(self):
        """Models that are always blocked from MCP access.

        Override in bridge modules using super() to add/remove entries.
        """
        return frozenset(
            {
                "res.users.apikeys",
                "res.users.apikeys.description",
                "res.users.apikeys.show",
                "ir.config_parameter",
                "mcp.session",
                "mcp.tool",
                "mcp.resource",
                "mcp.prompt",
                "mcp.prompt.argument",
                "mcp.access",
                "mcp.audit.log",
            }
        )

    @property
    def _blocked_methods(self):
        """Methods that are always blocked from method_call.

        Messaging methods (message_post, etc.) are NOT blocked here so that
        xf_mcp_mail bridge module can enable them. Override via super().
        """
        return frozenset(
            {
                # ORM write operations (use dedicated CRUD tools instead)
                "create",
                "write",
                "unlink",
                "copy",
                # ORM internals / privilege escalation
                "sudo",
                "with_user",
                "with_context",
                "with_env",
                "with_company",
                "browse",
                "flush_model",
                "flush_recordset",
                "invalidate_model",
                "invalidate_recordset",
                # Data export
                "export_data",
                "load",
                # Recordset traversal (can access blocked models)
                "mapped",
                "filtered",
                "sorted",
                "filtered_domain",
            }
        )

    @property
    def _smart_exclude_prefixes(self):
        """Field name prefixes to exclude from smart field defaults."""
        return (
            "message_",
            "activity_",
            "avatar_",
            "image_",
            "website_message_",
            "rating_",
        )

    @property
    def _smart_exclude_fields(self):
        """Specific field names to exclude from smart field defaults."""
        return frozenset(
            {
                "__last_update",
                "write_uid",
                "create_uid",
                "write_date",
                "create_date",
                "access_url",
                "access_token",
                "access_warning",
            }
        )

    @property
    def _smart_max_fields(self):
        """Maximum number of smart default fields to return."""
        return 20

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("input_schema")
    def _check_input_schema(self):
        for record in self:
            try:
                schema = json.loads(record.input_schema)
                if schema.get("type") != "object":
                    raise ValidationError(self.env._("Input schema 'type' must be 'object'."))
            except (json.JSONDecodeError, TypeError) as e:
                raise ValidationError(self.env._("Input schema must be valid JSON: %(error)s", error=e)) from e

    @api.constrains("annotations")
    def _check_annotations(self):
        for record in self:
            if record.annotations:
                try:
                    json.loads(record.annotations)
                except (json.JSONDecodeError, TypeError) as e:
                    raise ValidationError(self.env._("Annotations must be valid JSON: %(error)s", error=e)) from e

    def to_mcp_schema(self):
        """Convert tool record to MCP tools/list format."""
        self.ensure_one()
        result = {
            "name": self.name,
            "inputSchema": json.loads(self.input_schema),
        }
        if self.title:
            result["title"] = self.title
        if self.description:
            result["description"] = self.description
        if self.output_schema:
            result["outputSchema"] = json.loads(self.output_schema)
        if self.annotations:
            result["annotations"] = json.loads(self.annotations)
        return result

    # -------------------------------------------------------------------------
    # Tool execution helpers
    # -------------------------------------------------------------------------

    def _check_model_allowed(self, model_name, env):
        """Check if a model is accessible via MCP. Returns mcp.access record or None."""
        if model_name in self._blocked_models:
            raise UserError(self.env._("Access to model '%(model)s' is blocked.", model=model_name))
        if model_name not in env:
            raise UserError(self.env._("Model '%(model)s' does not exist.", model=model_name))
        # Check mcp.access overrides (include archived records to detect blocks)
        access = (
            env["mcp.access"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("model_name", "=", model_name),
                ],
                limit=1,
            )
        )
        if access and not access.active:
            raise UserError(self.env._("MCP access to model '%(model)s' is disabled.", model=model_name))
        # Return active access record for further checks, or None if no override
        return access if access and access.active else None

    def _check_operation(self, access, operation, user=None):
        """Check if operation is allowed by mcp.access record. No record = allowed."""
        if not access:
            return True
        # Check group restriction
        if access.group_ids and user:
            if not access.group_ids & user.group_ids:
                raise UserError(
                    self.env._(
                        "You are not in the required groups to access model '%(model)s' via MCP.",
                        model=access.model_name,
                    )
                )
        # Check operation permission
        field_map = {
            "read": "read_access",
            "write": "write_access",
            "create": "create_access",
            "delete": "delete_access",
            "method_call": "method_call_access",
        }
        field_name = field_map.get(operation)
        if field_name and not access[field_name]:
            raise UserError(
                self.env._(
                    "Operation '%(op)s' on model '%(model)s' is not allowed via MCP.",
                    op=operation,
                    model=access.model_name,
                )
            )
        return True

    def _filter_fields(self, access, field_names):
        """Filter fields based on mcp.access allowed_fields. No record or empty = all."""
        if not access or not access.allowed_fields:
            return field_names
        try:
            allowed = set(json.loads(access.allowed_fields))
        except (json.JSONDecodeError, TypeError):
            return field_names
        if not allowed:
            return field_names
        return [f for f in field_names if f in allowed]

    def _get_smart_fields(self, model):
        """Get smart default fields for a model when no fields specified."""
        result = ["id"]
        exclude_prefixes = self._smart_exclude_prefixes
        exclude_fields = self._smart_exclude_fields
        max_fields = self._smart_max_fields
        for fname, field in model._fields.items():
            if fname in ("id",) or fname.startswith("_"):
                continue
            if fname in exclude_fields:
                continue
            if any(fname.startswith(p) for p in exclude_prefixes):
                continue
            if field.type in ("binary", "one2many", "many2many"):
                continue
            result.append(fname)
            if len(result) >= max_fields:
                break
        # Always include display_name if available
        if "display_name" not in result and "display_name" in model._fields:
            result.insert(1, "display_name")
        return result

    def _coerce_list(self, value, param_name="parameter"):
        """Coerce a value to a list, JSON-parsing it if it arrives as a string.

        MCP clients may serialize array arguments as JSON strings instead of
        native JSON arrays. This helper handles both cases transparently.
        """
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                _logger.debug("Parameter '%s' is not JSON, wrapping as list", param_name)
            # Non-JSON string — wrap as single-element list
            return [value]
        raise UserError(self.env._("Parameter '%(name)s' must be a list.", name=param_name))

    def _coerce_dict(self, value, param_name="parameter"):
        """Coerce a value to a dict, JSON-parsing it if it arrives as a string."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                _logger.debug("Parameter '%s' is not valid JSON object", param_name)
        raise UserError(self.env._("Parameter '%(name)s' must be an object.", name=param_name))

    def _validate_domain(self, domain):
        """Validate an Odoo domain, return cleaned domain."""
        if not domain:
            return []
        if not isinstance(domain, list):
            raise UserError(self.env._("Domain must be a list."))
        if len(domain) > 50:
            raise UserError(self.env._("Domain must not exceed 50 clauses."))
        return domain

    def _check_method_allowed(self, method_name, access=None):
        """Check if a method is allowed for method_call."""
        if method_name.startswith("_"):
            raise UserError(self.env._("Private methods (starting with '_') are not allowed."))
        if method_name in self._blocked_methods:
            raise UserError(self.env._("Method '%(method)s' is blocked for security reasons.", method=method_name))
        if access and access.blocked_methods:
            try:
                blocked = json.loads(access.blocked_methods)
                if method_name in blocked:
                    raise UserError(
                        self.env._("Method '%(method)s' is blocked by MCP access configuration.", method=method_name)
                    )
            except (json.JSONDecodeError, TypeError):  # pylint: disable=except-pass
                pass

    def _format_records(self, records, field_names):  # pylint: disable=too-many-branches
        """Format recordset to list of dicts for AI consumption.

        Delegates to field.convert_to_read() for all standard types except:
        - many2one: returns {"id": N, "display_name": "..."} dict instead of the Odoo
          tuple (id, name) — dict is unambiguous for LLMs (JSON has no tuple type).
        - one2many/many2many: returns value.ids list — same as convert_to_read. ✅
        - binary: returns bool — convert_to_read returns raw bytes, leaking data to AI.
        - date: uses fields.Date.to_string() → "YYYY-MM-DD" — convert_to_read inherits
          base which returns the raw Python date object (not JSON-serializable).
        - datetime: uses fields.Datetime.to_string() → "YYYY-MM-DD HH:MM:SS" — same
          reason; base convert_to_read returns a raw datetime object.
        """
        result = []
        for record in records:  # pylint: disable=too-many-nested-blocks
            row = {}
            for fname in field_names:
                if fname not in record._fields:
                    continue
                field = record._fields[fname]
                try:
                    value = record[fname]
                    if field.type == "many2one":
                        # Dict is more LLM-friendly than convert_to_read's (id, name) tuple.
                        # Mirror convert_to_read: use sudo() so display_name resolves via
                        # the parent record's access rights, and handle MissingError for
                        # dangling FK references.
                        if value:
                            try:
                                row[fname] = {"id": value.id, "display_name": value.sudo().display_name}
                            except MissingError:
                                row[fname] = False
                        else:
                            row[fname] = False
                    elif field.type == "binary":
                        row[fname] = bool(value)
                    elif field.type == "date":
                        row[fname] = fields.Date.to_string(value) if value else False
                    elif field.type == "datetime":
                        # Convert UTC → user/context timezone before formatting.
                        # context_timestamp reads tz from record._context['tz'] first,
                        # then falls back to record.env.user.tz (user profile setting).
                        if value:
                            local_dt = fields.Datetime.context_timestamp(record, value)
                            row[fname] = fields.Datetime.to_string(local_dt)
                        else:
                            row[fname] = False
                    else:
                        # Delegate to Odoo's canonical serialization for all other types
                        row[fname] = field.convert_to_read(value, record)
                except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                    row[fname] = None
            result.append(row)
        return result

    # -------------------------------------------------------------------------
    # Tool execution methods (called by dispatcher)
    # -------------------------------------------------------------------------

    def _get_max_records(self):
        """Get configured max records limit."""
        return int(self.env["ir.config_parameter"].sudo().get_param("xf_mcp.max_records", "200"))

    def _execute_search(self, env, arguments):
        model_name = arguments.get("model")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "read", env.user)

        domain = self._validate_domain(self._coerce_list(arguments.get("domain", []), "domain"))
        requested_fields = self._coerce_list(arguments.get("fields", []), "fields")
        limit = min(int(arguments.get("limit", 10)), self._get_max_records())
        offset = int(arguments.get("offset", 0))
        order = arguments.get("order", False)

        model = env[model_name]
        if not requested_fields:
            requested_fields = self._get_smart_fields(model)
        requested_fields = self._filter_fields(access, requested_fields)

        records = model.search(domain, limit=limit, offset=offset, order=order)
        data = self._format_records(records, requested_fields)
        total = model.search_count(domain)

        return {
            "model": model_name,
            "records": data,
            "count": len(data),
            "total": total,
            "has_more": offset + len(data) < total,
        }

    def _execute_read(self, env, arguments):
        model_name = arguments.get("model")
        ids = self._coerce_list(arguments.get("ids", []), "ids")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "read", env.user)

        model = env[model_name]
        requested_fields = self._coerce_list(arguments.get("fields", []), "fields")
        if not requested_fields:
            requested_fields = self._get_smart_fields(model)
        requested_fields = self._filter_fields(access, requested_fields)

        records = model.browse(ids).exists()
        data = self._format_records(records, requested_fields)

        return {
            "model": model_name,
            "records": data,
            "count": len(data),
        }

    def _localize_datetime_values(self, model, values, env):
        """Convert datetime string values from context/user TZ to UTC before ORM write.

        Mirrors browser behavior: the web client converts local datetimes to UTC before
        sending to the server. Without this, an AI agent that reads "15:00" (local) and
        writes "15:00" back would store 15:00 UTC, reading back as 18:00 Moscow — wrong.

        Skips fields not present in model._fields and values that are not strings
        (e.g. False, None) to avoid touching already-UTC or empty values.
        """
        tz = env.tz
        if not tz:
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
                local_dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                local_aware = local_dt.replace(tzinfo=tz)
                utc_dt = local_aware.astimezone(UTC).replace(tzinfo=None)
                result[fname] = fields.Datetime.to_string(utc_dt)
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # leave as-is — malformed or ambiguous (DST fold)
        return result

    def _execute_create(self, env, arguments):
        model_name = arguments.get("model")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "create", env.user)

        model = env[model_name]
        values = arguments.get("values")
        values_list = arguments.get("values_list")

        if values_list:
            values_list = [
                self._localize_datetime_values(model, self._coerce_dict(v, "values_list item"), env)
                for v in self._coerce_list(values_list, "values_list")
            ]
            records = model.create(values_list)
        elif values:
            values = self._localize_datetime_values(model, self._coerce_dict(values, "values"), env)
            records = model.create(values)
        else:
            raise UserError(self.env._("Provide 'values' for a single record or 'values_list' for batch create."))

        return {
            "model": model_name,
            "ids": records.ids,
            "count": len(records),
        }

    def _execute_write(self, env, arguments):
        model_name = arguments.get("model")
        ids = self._coerce_list(arguments.get("ids", []), "ids")
        values = self._coerce_dict(arguments.get("values", {}), "values")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "write", env.user)

        model = env[model_name]
        records = model.browse(ids).exists()
        values = self._localize_datetime_values(model, values, env)
        records.write(values)

        return {
            "model": model_name,
            "ids": records.ids,
            "updated": len(records),
        }

    def _execute_unlink(self, env, arguments):
        model_name = arguments.get("model")
        ids = self._coerce_list(arguments.get("ids", []), "ids")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "delete", env.user)

        records = env[model_name].browse(ids).exists()
        count = len(records)
        records.unlink()

        return {
            "model": model_name,
            "deleted": count,
        }

    def _execute_count(self, env, arguments):
        model_name = arguments.get("model")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "read", env.user)

        domain = self._validate_domain(self._coerce_list(arguments.get("domain", []), "domain"))
        count = env[model_name].search_count(domain)

        return {
            "model": model_name,
            "count": count,
        }

    def _execute_read_group(self, env, arguments):
        model_name = arguments.get("model")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))

        groupby = self._coerce_list(arguments.get("groupby"), "groupby")
        if not groupby:
            raise UserError(self.env._("Parameter 'groupby' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "read", env.user)

        domain = self._validate_domain(self._coerce_list(arguments.get("domain", []), "domain"))
        field_specs = self._coerce_list(arguments.get("fields", []), "fields")
        limit = arguments.get("limit")
        offset = arguments.get("offset", 0)
        orderby = arguments.get("orderby", False)
        lazy = arguments.get("lazy", False)

        raw_groups = env[model_name].formatted_read_group(
            domain=domain,
            fields=field_specs,
            groupby=groupby,
            offset=offset,
            limit=limit,
            orderby=orderby,
            lazy=lazy,
        )

        # Strip internal Odoo keys (__domain, __context) — large and not useful for AI.
        # Keep __count and __range (count per group, date range metadata).
        def _clean_group(group):
            result = {}
            for key, val in group.items():
                if key in ("__domain", "__context"):
                    continue
                # Many2one fields return (id, display_name) tuples — normalize to dict
                if isinstance(val, tuple) and len(val) == 2:
                    result[key] = {"id": val[0], "display_name": val[1]}
                else:
                    result[key] = val
            return result

        groups = [_clean_group(g) for g in raw_groups]

        return {
            "model": model_name,
            "groupby": groupby,
            "groups": groups,
            "count": len(groups),
        }

    def _execute_default_get(self, env, arguments):
        model_name = arguments.get("model")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "read", env.user)

        field_list = arguments.get("fields", [])
        if not field_list:
            field_list = list(env[model_name]._fields.keys())

        defaults = env[model_name].default_get(field_list)

        return {
            "model": model_name,
            "defaults": defaults,
        }

    def _execute_list_modules(self, env, arguments):
        keyword = arguments.get("keyword", "")
        state = arguments.get("state", "installed")

        domain = [("state", "=", state)]
        if keyword:
            domain.append(("name", "ilike", keyword))

        modules = env["ir.module.module"].sudo().search(domain, limit=self._get_max_records())
        return {
            "modules": [
                {
                    "name": m.name,
                    "shortdesc": m.shortdesc,
                    "state": m.state,
                    "installed_version": m.installed_version or "",
                    "summary": m.summary or "",
                }
                for m in modules
            ],
            "count": len(modules),
        }

    def _execute_list_companies(self, env, _arguments):
        """Return companies accessible to the current user."""
        user = env.user
        return {
            "current_company_id": user.company_id.id,
            "current_company_name": user.company_id.name,
            "companies": [{"id": c.id, "name": c.name} for c in user.company_ids],
            "hint": (
                "To operate in a specific company, pass "
                "context={'allowed_company_ids': [<company_id>]} to create/write/method_call tools."
            ),
        }

    def _execute_method_call(self, env, arguments):
        model_name = arguments.get("model")
        method_name = arguments.get("method")
        if not model_name:
            raise UserError(self.env._("Parameter 'model' is required."))
        if not method_name:
            raise UserError(self.env._("Parameter 'method' is required."))

        access = self._check_model_allowed(model_name, env)
        self._check_operation(access, "method_call", env.user)
        self._check_method_allowed(method_name, access)

        ids = self._coerce_list(arguments.get("ids", []), "ids")
        args = self._coerce_list(arguments.get("args", []), "args")
        kwargs = self._coerce_dict(arguments.get("kwargs", {}), "kwargs")

        model = env[model_name]
        if ids:
            records = model.browse(ids).exists()
        else:
            records = model

        method = getattr(records, method_name, None)
        if method is None or not callable(method):
            raise UserError(
                self.env._("Method '%(method)s' not found on model '%(model)s'.", method=method_name, model=model_name)
            )

        # Strip privilege escalation keys from kwargs
        safe_kwargs = {k: v for k, v in kwargs.items() if k not in _BLOCKED_KWARGS}
        result = method(*args, **safe_kwargs)
        return self._serialize_method_result(result)

    def _serialize_method_result(self, value):
        """Serialize a method call result to JSON-safe format."""
        if value is None or isinstance(value, bool | int | float | str):
            return {"result": value}
        if isinstance(value, dict):
            return {"result": {k: self._serialize_value(v) for k, v in value.items()}}
        if isinstance(value, list | tuple):
            return {"result": [self._serialize_value(v) for v in value]}
        if hasattr(value, "_name") and hasattr(value, "ids"):
            # Recordset
            return {"result": {"model": value._name, "ids": value.ids}}
        return {"result": str(value)}

    def _serialize_value(self, value):
        if value is None or isinstance(value, bool | int | float | str):
            return value
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self._serialize_value(v) for v in value]
        if hasattr(value, "_name") and hasattr(value, "ids"):
            return {"model": value._name, "ids": value.ids}
        return str(value)

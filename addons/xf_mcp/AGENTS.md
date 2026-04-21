# xf_mcp — MCP Server

Native Model Context Protocol (MCP) server for Odoo. Exposes tools, resources, and prompts to AI assistants (Claude,
Cursor, VS Code) over Streamable HTTP transport with JSON-RPC 2.0.

## Dependencies

| Module | What it provides to this module                                                               |
| ------ | --------------------------------------------------------------------------------------------- |
| `base` | Standard Odoo models, `res.users`, `res.groups`, `ir.model`, `ir.config_parameter`, `ir.cron` |

## Key Files

| File                            | Purpose                                                                                                                            |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `post_load.py`                  | Patches `Request._post_init` to resolve `?db=` query param on `/mcp` — required for multi-DB setups without a prior session cookie |
| `controllers/mcp.py`            | Single `/mcp` HTTP endpoint (POST/GET/DELETE/OPTIONS), request lifecycle, CORS, audit logging                                      |
| `services/auth.py`              | Bearer token auth, rate limiting (thread-safe), IP filtering (CIDR), brute force protection                                        |
| `services/dispatcher.py`        | JSON-RPC parsing, protocol negotiation, MCP method dispatch, `JsonRpcError` class                                                  |
| `models/mcp_tool.py`            | Tool registry + 10 `_execute_*` methods + `BLOCKED_MODELS`/`BLOCKED_METHODS` constants                                             |
| `models/mcp_resource.py`        | Resource registry + URI template matching + 6 `_resolve_*` methods                                                                 |
| `models/mcp_prompt.py`          | Prompt + argument models, template rendering via `str.format()`                                                                    |
| `models/mcp_access.py`          | Optional per-model access overrides (restriction layer on top of Odoo ACL)                                                         |
| `models/mcp_session.py`         | Session create/find/touch/cleanup with crypto-random IDs                                                                           |
| `models/mcp_audit_log.py`       | Audit trail with truncation and cron cleanup                                                                                       |
| `models/res_config_settings.py` | Settings fields for all `xf_mcp.*` config parameters                                                                               |
| `data/mcp_tools_data.xml`       | 10 default tool records (`noupdate="1"`)                                                                                           |
| `data/mcp_resources_data.xml`   | 6 default resource records (`noupdate="1"`)                                                                                        |
| `data/mcp_defaults.xml`         | System parameters defaults, 2 cron jobs                                                                                            |
| `security/mcp_security.xml`     | Groups (`group_mcp_user`, `group_mcp_admin`), record rules                                                                         |

## Models

### `mcp.session` (McpSession)

**Type:** Model

| Field              | Type                | Notes                                                                    |
| ------------------ | ------------------- | ------------------------------------------------------------------------ |
| `session_id`       | Char                | required, index, readonly, crypto-random via `secrets.token_urlsafe(32)` |
| `user_id`          | Many2one(res.users) | required, ondelete=cascade                                               |
| `protocol_version` | Char                | negotiated MCP version                                                   |
| `client_info`      | Text                | JSON string                                                              |
| `active`           | Boolean             | deactivated on expiry or DELETE                                          |

- `create_session(user_id, protocol_version, client_info)` — generates session_id
- `find_session(session_id)` — returns active session or empty
- `touch()` — updates `last_activity`
- `cleanup_expired(ttl_hours)` — cron entry point

### `mcp.tool` (McpTool)

**Type:** Model

| Field          | Type      | Notes                                     |
| -------------- | --------- | ----------------------------------------- |
| `name`         | Char      | unique, tool identifier                   |
| `input_schema` | Text      | JSON Schema, type must be "object"        |
| `method_name`  | Char      | e.g. `_execute_search`                    |
| `category`     | Selection | crud/discovery/custom                     |
| `annotations`  | Text      | JSON: readOnlyHint, destructiveHint, etc. |

- `to_mcp_schema()` — converts to MCP `tools/list` format
- `_check_model_allowed(model_name, env)` — blocked models → mcp.access check (uses `active_test=False`)
- `_check_operation(access, operation, user)` — group_ids + CRUD flag check
- `_filter_fields(access, field_names)` — allowed_fields from mcp.access
- `_get_smart_fields(model)` — auto-selects ~20 fields, excludes binary/o2m/m2m/metadata, always includes id +
  display_name
- `_validate_domain(domain)` — max 50 clauses
- `_check_method_allowed(method_name, access)` — blocked methods + per-model blocks
- `_format_records(records, field_names)` — handles m2o as `{id, display_name}`, binary as bool, dates as strings
- `_execute_search/read/create/write/unlink/count/read_group/default_get/list_modules/method_call` — tool
  implementations

### `mcp.resource` (McpResource)

**Type:** Model

| Field         | Type    | Notes                                         |
| ------------- | ------- | --------------------------------------------- |
| `uri_pattern` | Char    | unique, static URI or template with `{param}` |
| `is_template` | Boolean | computed, True if `{` in uri_pattern          |
| `method_name` | Char    | e.g. `_resolve_system_info`                   |

- `resolve_uri(uri)` — sudo for registry lookup, caller env for data access
- `_match_uri(uri)` — regex-based URI template matching
- `_resolve(uri, params, caller_env)` — dispatches to resolver method
- `_resolve_system_info/user_me/model_schema/model_access/module_info/record` — resource implementations

### `mcp.prompt` (McpPrompt)

**Type:** Model

| Field              | Type                          | Notes                                           |
| ------------------ | ----------------------------- | ----------------------------------------------- |
| `name`             | Char                          | unique per scope (partial indexes via `init()`) |
| `is_global`        | Boolean                       | True = admin, False = personal                  |
| `user_id`          | Many2one(res.users)           | required when is_global=False                   |
| `message_template` | Text                          | `{arg_name}` placeholders                       |
| `role`             | Selection                     | user/assistant                                  |
| `argument_ids`     | One2many(mcp.prompt.argument) |                                                 |

- `init()` — creates partial unique indexes on PostgreSQL
- `render(arguments)` — validates required args, calls `str.format(**arguments)`
- User prompt names cannot conflict with global prompt names (Python constraint)

### `mcp.access` (McpAccess)

**Type:** Model — Optional restriction layer on top of Odoo ACL

| Field                                         | Type                  | Notes                        |
| --------------------------------------------- | --------------------- | ---------------------------- |
| `model_id`                                    | Many2one(ir.model)    | unique constraint            |
| `read/write/create/delete/method_call_access` | Boolean               | all default True             |
| `allowed_fields`                              | Text                  | JSON list, empty = all       |
| `blocked_methods`                             | Text                  | JSON list, additional blocks |
| `group_ids`                                   | Many2many(res.groups) | empty = all MCP users        |

- If no record exists for a model → Odoo ACL is sole authority
- If record exists with `active=False` → model entirely blocked from MCP
- Can only restrict, never grant more than Odoo ACL

### `mcp.audit.log` (McpAuditLog)

**Type:** Model

- `log_request(vals)` — truncates request_data to 5000 chars
- `cron_cleanup_old_logs()` — deletes older than `xf_mcp.log_retention_days`

## Architecture Overview

```
HTTP POST /mcp
  └─ McpController.mcp_endpoint()
     ├─ check enabled (ir.config_parameter)
     ├─ check IP filtering (auth.check_ip_filtering)
     ├─ parse JSON-RPC (dispatcher.parse_request)
     ├─ authenticate (auth.authenticate_request → Bearer token)
     ├─ check group_mcp_user
     ├─ validate MCP-Session-Id header (except initialize)
     ├─ check rate limit (auth.check_rate_limit)
     ├─ dispatch to handler (dispatcher.handle_*)
     │   ├─ initialize → create session, return capabilities
     │   ├─ tools/call → env.cr.savepoint() → mcp.tool._execute_*(env, arguments)
     │   ├─ resources/read → mcp.resource.resolve_uri(uri)
     │   └─ prompts/get → mcp.prompt.render(arguments)
     ├─ except ValidationError/AccessError/UserError → JSON-RPC error (HTTP 200, not 500)
     └─ audit log — status="error" if result.isError else "success"
```

## Important Constants / Mappings

```python
# mcp_tool.py
BLOCKED_MODELS = frozenset({  # 11 models always blocked
    "res.users.apikeys", "ir.config_parameter",
    "mcp.session", "mcp.tool", "mcp.resource", "mcp.prompt",
    "mcp.prompt.argument", "mcp.access", "mcp.audit.log", ...
})

BLOCKED_METHODS = frozenset({  # 18 methods always blocked from method_call
    "create", "write", "unlink", "copy", "sudo", "with_user",
    "with_context", "with_env", "with_company", "browse",
    "export_data", "load", "import_data", "message_post",
    "mapped", "filtered", "sorted", "filtered_domain", ...
})

# dispatcher.py
SUPPORTED_VERSIONS = ["2025-11-25", "2024-11-05"]
```

## Configuration / Settings Fields

```python
xf_mcp.enabled                  # Boolean — master switch (default: False)
xf_mcp.rate_limit               # Integer — req/min per user (default: 60)
xf_mcp.max_records              # Integer — max records per response (default: 200)
xf_mcp.ip_filtering_enabled     # Boolean — enable IP filtering (default: False)
xf_mcp.ip_filtering_strategy    # String — "allow_list" or "deny_list"
xf_mcp.ip_list                  # Text — one IP/CIDR per line
xf_mcp.logging_enabled          # Boolean — audit logging (default: True)
xf_mcp.log_retention_days       # Integer — days to keep logs (default: 90)
xf_mcp.session_ttl_hours        # Integer — session expiry (default: 24)
xf_mcp.allowed_origins          # Char — CORS origins, comma-separated
```

## Cron Jobs

| Method                                   | Schedule | Active |
| ---------------------------------------- | -------- | ------ |
| `mcp.audit.log.cron_cleanup_old_logs()`  | Daily    | Yes    |
| `mcp.session.cleanup_expired(ttl_hours)` | Hourly   | Yes    |

## Security Groups

| XML ID            | Name              | Implies          |
| ----------------- | ----------------- | ---------------- |
| `group_mcp_user`  | MCP User          | —                |
| `group_mcp_admin` | MCP Administrator | `group_mcp_user` |

## Patterns / Conventions

- **Auth runs on every request** — `auth='none'` on controller, manual auth in `_handle_post()`
- **sudo for registry, user env for data** — tool/resource records looked up with sudo, but ORM calls on business data
  use authenticated user's env so Odoo ACL applies
- **noupdate=1 on data records** — default tools/resources survive module upgrade, admin customizations preserved
- **Tool errors are not protocol errors** — tool exceptions return `{isError: true}` in MCP result, not JSON-RPC errors;
  Odoo app exceptions (`ValidationError`/`AccessError`/`UserError`) raised outside `tools/call` are caught at the
  controller level and returned as JSON-RPC error responses (HTTP 200)
- **Tool execution uses savepoint** — `handle_tools_call` wraps `method()` in `env.cr.savepoint()` so DB-level errors
  (FK violations, etc.) roll back cleanly without aborting the outer transaction (and breaking the audit log)
- **Multi-DB via `?db=` query param** — `post_load.py` patches `Request._post_init`; without it the `/mcp` route is
  invisible in nodb mode for clients that haven't established a session cookie first
- **Smart field defaults** — when no fields requested, auto-selects ~20 non-binary non-relational fields with id +
  display_name always first
- **Rate limiting is in-memory** — thread-safe dicts with Lock, lost on restart, per-process only (not distributed)
- **Partial unique indexes** — `mcp.prompt` uses `init()` to create PostgreSQL partial indexes (Odoo `_sql_constraints`
  doesn't support WHERE)

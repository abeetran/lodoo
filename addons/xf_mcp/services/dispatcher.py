import json
import logging

_logger = logging.getLogger(__name__)

# Supported protocol versions (newest first)
SUPPORTED_VERSIONS = ["2024-11-05"]
SERVER_VERSION = SUPPORTED_VERSIONS[0]

# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
RESOURCE_NOT_FOUND = -32002

# Context keys that are safe to propagate from AI agent to Odoo env
_ALLOWED_CTX_KEYS = frozenset(
    {
        "lang",
        "tz",
        "allowed_company_ids",
        "active_test",
        "no_recompute",
    }
)

# MCP method → internal handler key mapping
HANDLERS = {
    "initialize": "initialize",
    "notifications/initialized": "notification",
    "notifications/cancelled": "notification",
    "notifications/progress": "notification",
    "ping": "ping",
    "tools/list": "tools_list",
    "tools/call": "tools_call",
    "resources/list": "resources_list",
    "resources/templates/list": "resources_templates_list",
    "resources/read": "resources_read",
    "prompts/list": "prompts_list",
    "prompts/get": "prompts_get",
}


def make_response(rpc_id, result):
    """Build a JSON-RPC success response."""
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": result,
    }


def make_error(rpc_id, code, message, data=None):
    """Build a JSON-RPC error response."""
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": error,
    }


def parse_request(raw_body):
    """Parse raw request body into JSON-RPC message. Returns (rpc_id, method, params) or raises."""
    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError) as e:
        raise JsonRpcError(None, PARSE_ERROR, f"Parse error: {e}") from e

    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        raise JsonRpcError(body.get("id"), INVALID_REQUEST, "Invalid JSON-RPC 2.0 request.")

    method = body.get("method")
    if not method:
        raise JsonRpcError(body.get("id"), INVALID_REQUEST, "Missing 'method' field.")

    return body.get("id"), method, body.get("params", {})


def handle_initialize(params, env, session_model):
    """Handle initialize request. Returns (result, session_record)."""
    client_version = params.get("protocolVersion", "")
    client_info = params.get("clientInfo", {})

    # Negotiate protocol version
    if client_version in SUPPORTED_VERSIONS:
        negotiated_version = client_version
    else:
        negotiated_version = SERVER_VERSION

    # Create session
    session = session_model.create_session(
        user_id=env.uid,
        protocol_version=negotiated_version,
        client_info=json.dumps(client_info) if client_info else None,
    )

    # Read configurable system instructions
    instructions = env["ir.config_parameter"].sudo().get_param("xf_mcp.system_instructions", "") or (
        "You are connected to an Odoo ERP system via the MCP protocol. "
        "Use resources to discover models and schemas before calling tools. "
        "All operations run with your Odoo user permissions. "
        "For multi-language setups, pass context={'lang': 'en_US'} (or your language code) "
        "on tool calls to get translated field values. "
        "For multi-company setups, pass context={'allowed_company_ids': [company_id]} "
        "on create/write/method_call operations."
    )

    # Include authenticated user context so AI agents know defaults to use
    user = env.user
    result = {
        "protocolVersion": negotiated_version,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
            "logging": {},
        },
        "serverInfo": {
            "name": "xf_mcp",
            "title": "Odoo MCP Server",
            "version": "19.0.1.0.0",
            "user": {
                "id": user.id,
                "name": user.name,
                "lang": user.lang or "en_US",
                "tz": user.tz or "UTC",
                "company_id": user.company_id.id,
                "company_name": user.company_id.name,
            },
        },
        "instructions": instructions,
    }
    return result, session


def handle_ping():
    """Handle ping request."""
    return {}


def handle_tools_list(env):
    """Handle tools/list request."""
    tools = env["mcp.tool"].sudo().search([("active", "=", True)])
    return {
        "tools": [tool.to_mcp_schema() for tool in tools],
    }


def _apply_context(arguments, env):
    """Extract and apply context from tool arguments. Returns (updated_env, cleaned_arguments)."""
    ctx = arguments.get("context")
    if not ctx or not isinstance(ctx, dict):
        return env, arguments

    # Whitelist safe keys only
    safe_ctx = {k: v for k, v in ctx.items() if k in _ALLOWED_CTX_KEYS}
    if safe_ctx:
        env = env(context={**env.context, **safe_ctx})

    # Remove context from arguments before passing to tool
    cleaned = {k: v for k, v in arguments.items() if k != "context"}
    return env, cleaned


def handle_tools_call(params, env):
    """Handle tools/call request. Returns MCP tool result."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        raise JsonRpcError(None, INVALID_PARAMS, "Missing 'name' parameter.")

    tool = env["mcp.tool"].sudo().search([("name", "=", tool_name), ("active", "=", True)], limit=1)
    if not tool:
        raise JsonRpcError(None, INVALID_PARAMS, f"Unknown tool: {tool_name}")

    # Apply user-provided context (lang, tz, allowed_company_ids, etc.)
    env, arguments = _apply_context(arguments, env)

    method = getattr(tool, tool.method_name, None)
    if method is None:
        raise JsonRpcError(None, INTERNAL_ERROR, f"Tool method not found: {tool.method_name}")

    # Use a savepoint so DB-level errors (FK violations, etc.) don't abort the
    # outer transaction and prevent the subsequent audit log write from failing.
    # flush=False (plain Savepoint) is intentional: _FlushingSavepoint.rollback()
    # calls cr.clear() → Transaction.clear() → cache.clear(), which wipes the
    # ormcache for ir.config_parameter._get_param and causes KeyError in the
    # subsequent get_param() calls inside _log_request / _get_cors_headers.
    # Plain SQL SAVEPOINT/ROLLBACK TO SAVEPOINT is sufficient here.
    try:
        with env.cr.savepoint(flush=False):
            result = method(env, arguments)
    except Exception as e:  # pylint: disable=broad-exception-caught
        _logger.exception("MCP tool %r raised an error", tool_name)
        return {
            "content": [{"type": "text", "text": f"Error: {e}"}],
            "isError": True,
        }

    return {
        "content": [{"type": "text", "text": json.dumps(result, default=str)}],
        "isError": False,
    }


def handle_resources_list(env):
    """Handle resources/list request."""
    resources = (
        env["mcp.resource"]
        .sudo()
        .search(
            [
                ("active", "=", True),
                ("is_template", "=", False),
            ]
        )
    )
    return {
        "resources": [r.to_mcp_resource() for r in resources],
    }


def handle_resources_templates_list(env):
    """Handle resources/templates/list request."""
    templates = (
        env["mcp.resource"]
        .sudo()
        .search(
            [
                ("active", "=", True),
                ("is_template", "=", True),
            ]
        )
    )
    return {
        "resourceTemplates": [t.to_mcp_template() for t in templates],
    }


def handle_resources_read(params, env):
    """Handle resources/read request."""
    uri = params.get("uri")
    if not uri:
        raise JsonRpcError(None, INVALID_PARAMS, "Missing 'uri' parameter.")

    result = env["mcp.resource"].resolve_uri(uri)
    if result is None:
        raise JsonRpcError(None, RESOURCE_NOT_FOUND, f"No resource found for URI: {uri}")

    return result


def handle_prompts_list(env):
    """Handle prompts/list request."""
    # Global prompts + user's personal prompts
    prompts = env["mcp.prompt"].search(
        [
            "|",
            ("is_global", "=", True),
            ("user_id", "=", env.uid),
        ]
    )
    return {
        "prompts": [p.to_mcp_prompt() for p in prompts],
    }


def handle_prompts_get(params, env):
    """Handle prompts/get request."""
    name = params.get("name")
    arguments = params.get("arguments", {})

    if not name:
        raise JsonRpcError(None, INVALID_PARAMS, "Missing 'name' parameter.")

    # Personal prompt takes precedence over global
    prompt = env["mcp.prompt"].search(
        [
            ("name", "=", name),
            ("user_id", "=", env.uid),
            ("is_global", "=", False),
        ],
        limit=1,
    )

    if not prompt:
        prompt = env["mcp.prompt"].search(
            [
                ("name", "=", name),
                ("is_global", "=", True),
            ],
            limit=1,
        )

    if not prompt:
        raise JsonRpcError(None, RESOURCE_NOT_FOUND, f"Prompt not found: {name}")

    return prompt.render(arguments)


class JsonRpcError(Exception):
    """JSON-RPC error with code and message."""

    def __init__(self, rpc_id, code, message):
        super().__init__(message)
        self.rpc_id = rpc_id
        self.code = code
        self.message = message

    def to_response(self):
        return make_error(self.rpc_id, self.code, self.message)

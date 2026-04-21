import json
import logging
import queue
import threading
import time
import uuid

from werkzeug.wrappers import Response as WerkzeugResponse

from odoo import http
from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.http import request
from odoo.tools.convert import str2bool

from ..services.auth import (
    authenticate_request,
    check_auth_rate_limit,
    check_ip_filtering,
    check_rate_limit,
    get_client_ip,
    get_user_agent,
    record_auth_failure,
)
from ..services.dispatcher import (
    HANDLERS,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcError,
    handle_initialize,
    handle_ping,
    handle_prompts_get,
    handle_prompts_list,
    handle_resources_list,
    handle_resources_read,
    handle_resources_templates_list,
    handle_tools_call,
    handle_tools_list,
    make_error,
    make_response,
    parse_request,
)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP+SSE transport session store
# Each entry: {'queue': Queue, 'uid': int, 'db': str}
# Created on GET /mcp (SSE open), destroyed when connection closes.
# ---------------------------------------------------------------------------
_sse_sessions: dict = {}
_sse_lock = threading.Lock()


class McpController(http.Controller):
    """MCP endpoint supporting both transports:

    - Streamable HTTP (POST /mcp): used by Claude Desktop, Claude Code, etc.
    - HTTP+SSE (GET /mcp → SSE stream, POST /mcp/message): used by LM Studio, older clients.
    """

    @http.route(
        "/mcp",
        type="http",
        auth="none",
        methods=["POST", "GET", "DELETE", "OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def mcp_endpoint(self, **_kwargs):
        method = request.httprequest.method

        if method == "OPTIONS":
            return self._cors_preflight()

        if method == "GET":
            return self._handle_get_sse()

        if method == "DELETE":
            return self._handle_delete()

        # POST — Streamable HTTP transport
        return self._handle_post()

    @http.route(
        "/mcp/message",
        type="http",
        auth="none",
        methods=["POST", "OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def mcp_message_endpoint(self, **_kwargs):
        """HTTP+SSE transport: receive client→server message, respond via SSE stream."""
        if request.httprequest.method == "OPTIONS":
            return self._cors_preflight()
        env = request.env
        sse_enabled = env["ir.config_parameter"].sudo().get_param("xf_mcp.sse_enabled", "True")
        if not str2bool(sse_enabled):
            return self._make_json_response(make_error(None, INTERNAL_ERROR, "SSE transport is disabled."), status=405)
        return self._handle_sse_message()

    # -------------------------------------------------------------------------
    # POST handler
    # -------------------------------------------------------------------------

    def _handle_post(self):  # pylint: disable=too-many-locals,too-many-return-statements,too-complex,too-many-branches,too-many-statements
        start_time = time.time()
        env = request.env
        rpc_id = None
        mcp_method = None
        params = {}
        session = None
        user = None

        try:
            # Check MCP enabled
            enabled = env["ir.config_parameter"].sudo().get_param("xf_mcp.enabled", "False")
            if not str2bool(enabled):
                return self._make_json_response(
                    make_error(None, INTERNAL_ERROR, "MCP server is disabled."),
                    status=503,
                )

            # Check IP filtering
            if not check_ip_filtering(request, env):
                return self._make_json_response(
                    make_error(None, INTERNAL_ERROR, "IP address not allowed."),
                    status=403,
                )

            # Parse JSON-RPC message
            raw_body = request.httprequest.get_data(as_text=True)
            try:
                rpc_id, mcp_method, params = parse_request(raw_body)
            except JsonRpcError as e:
                return self._make_json_response(e.to_response(), status=400)

            # Check if method is known
            handler_key = HANDLERS.get(mcp_method)
            if handler_key is None:
                return self._make_json_response(
                    make_error(rpc_id, METHOD_NOT_FOUND, f"Unknown method: {mcp_method}"),
                    status=200,
                )

            # Handle notifications (no response needed)
            if handler_key == "notification":
                return self._make_http_response("", status=204)

            # Authenticate
            client_ip = get_client_ip(request)
            allowed, retry_after = check_auth_rate_limit(client_ip)
            if not allowed:
                return self._make_json_response(
                    make_error(rpc_id, INTERNAL_ERROR, "Too many auth failures."),
                    status=429,
                    headers={"Retry-After": str(retry_after)},
                )

            try:
                uid, user, _db_name = authenticate_request(request)
            except AccessDenied as e:
                record_auth_failure(client_ip)
                # Log the failed auth attempt to audit trail
                self._log_auth_failure(env, mcp_method, str(e), start_time)
                return self._make_json_response(
                    make_error(rpc_id, INTERNAL_ERROR, str(e)),
                    status=401,
                )

            # Switch to authenticated user environment
            env = request.env(user=uid)

            # Check MCP group
            if not user.has_group("xf_mcp.group_mcp_user"):
                return self._make_json_response(
                    make_error(rpc_id, INTERNAL_ERROR, "User not in MCP group."),
                    status=403,
                )

            # For non-initialize requests, validate session
            if mcp_method != "initialize":
                session_id = request.httprequest.headers.get("MCP-Session-Id", "")
                if not session_id:
                    return self._make_json_response(
                        make_error(rpc_id, INVALID_REQUEST, "Missing MCP-Session-Id header."),
                        status=400,
                    )
                session = env["mcp.session"].find_session(session_id)
                if not session:
                    return self._make_json_response(
                        make_error(rpc_id, INVALID_REQUEST, "Invalid or expired session."),
                        status=404,
                    )
                session.touch()

            # Rate limiting
            rate_limit = int(env["ir.config_parameter"].sudo().get_param("xf_mcp.rate_limit", "60"))
            allowed, retry_after = check_rate_limit(uid, rate_limit)
            if not allowed:
                return self._make_json_response(
                    make_error(rpc_id, INTERNAL_ERROR, "Rate limit exceeded."),
                    status=429,
                    headers={"Retry-After": str(retry_after)},
                )

            # Dispatch to handler
            result, new_session = self._dispatch(handler_key, rpc_id, params, env)

            # Build response
            response_body = make_response(rpc_id, result)
            headers = {}

            # Include session ID header for initialize
            if new_session:
                headers["MCP-Session-Id"] = new_session.session_id
                session = new_session

            # Audit log — tools/call may return isError:True for ORM/validation errors
            is_tool_error = isinstance(result, dict) and result.get("isError", False)
            audit_error_msg = None
            if is_tool_error:
                try:
                    audit_error_msg = result["content"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    audit_error_msg = "Tool execution error"
            self._log_request(
                env=env,
                session=session,
                user=user,
                mcp_method=mcp_method,
                params=params,
                status="error" if is_tool_error else "success",
                error_message=audit_error_msg,
                start_time=start_time,
            )

            return self._make_json_response(response_body, headers=headers)

        except JsonRpcError as e:
            self._log_request(
                env=env,
                session=session,
                user=user,
                mcp_method=mcp_method,
                params={},
                status="error",
                error_message=str(e),
                start_time=start_time,
            )
            return self._make_json_response(e.to_response())

        except (ValidationError, AccessError, UserError) as e:
            # Odoo application exceptions should return a JSON-RPC error (not HTTP 500)
            msg = e.args[0] if e.args else str(e)
            self._log_request(
                env=env,
                session=session,
                user=user,
                mcp_method=mcp_method,
                params=params,
                status="error",
                error_message=msg,
                start_time=start_time,
            )
            return self._make_json_response(
                make_error(rpc_id, INTERNAL_ERROR, msg),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            _logger.exception("MCP internal error")
            self._log_request(
                env=env,
                session=session,
                user=user,
                mcp_method=mcp_method,
                params={},
                status="error",
                error_message=str(e),
                start_time=start_time,
            )
            return self._make_json_response(
                make_error(rpc_id, INTERNAL_ERROR, "Internal server error."),
                status=500,
            )

    def _dispatch(self, handler_key, rpc_id, params, env):
        """Dispatch to the appropriate handler. Returns (result, new_session_or_None)."""
        new_session = None

        if handler_key == "initialize":
            result, new_session = handle_initialize(params, env, env["mcp.session"])
        elif handler_key == "ping":
            result = handle_ping()
        elif handler_key == "tools_list":
            result = handle_tools_list(env)
        elif handler_key == "tools_call":
            result = handle_tools_call(params, env)
        elif handler_key == "resources_list":
            result = handle_resources_list(env)
        elif handler_key == "resources_templates_list":
            result = handle_resources_templates_list(env)
        elif handler_key == "resources_read":
            result = handle_resources_read(params, env)
        elif handler_key == "prompts_list":
            result = handle_prompts_list(env)
        elif handler_key == "prompts_get":
            result = handle_prompts_get(params, env)
        else:
            raise JsonRpcError(rpc_id, METHOD_NOT_FOUND, f"No handler for: {handler_key}")

        return result, new_session

    # -------------------------------------------------------------------------
    # HTTP+SSE transport — GET opens stream, POST /mcp/message sends messages
    # -------------------------------------------------------------------------

    def _handle_get_sse(self):  # pylint: disable=too-many-locals,too-many-return-statements
        """HTTP+SSE transport: open server-to-client SSE stream.

        Authenticates the client, creates an in-memory SSE session, and streams:
          1. An 'endpoint' event with the URL the client should POST messages to.
          2. 'message' events containing JSON-RPC responses.
          3. Keep-alive ping comments every 30 s.
        """
        env = request.env

        # Security checks (same as POST path)
        enabled = env["ir.config_parameter"].sudo().get_param("xf_mcp.enabled", "False")
        if not str2bool(enabled):
            return self._make_json_response(make_error(None, INTERNAL_ERROR, "MCP server is disabled."), status=503)
        sse_enabled = env["ir.config_parameter"].sudo().get_param("xf_mcp.sse_enabled", "True")
        if not str2bool(sse_enabled):
            return self._make_json_response(make_error(None, INTERNAL_ERROR, "SSE transport is disabled."), status=405)
        if not check_ip_filtering(request, env):
            return self._make_json_response(make_error(None, INTERNAL_ERROR, "IP address not allowed."), status=403)

        client_ip = get_client_ip(request)
        allowed, retry_after = check_auth_rate_limit(client_ip)
        if not allowed:
            return self._make_json_response(
                make_error(None, INTERNAL_ERROR, "Too many auth failures."),
                status=429,
                headers={"Retry-After": str(retry_after)},
            )

        try:
            uid, user, _db_name = authenticate_request(request)
        except AccessDenied as e:
            record_auth_failure(client_ip)
            return self._make_json_response(make_error(None, INTERNAL_ERROR, str(e)), status=401)

        env = request.env(user=uid)
        if not user.has_group("xf_mcp.group_mcp_user"):
            return self._make_json_response(make_error(None, INTERNAL_ERROR, "User not in MCP group."), status=403)

        # Create SSE session
        sse_id = str(uuid.uuid4())
        q: queue.Queue = queue.Queue()
        db = request.db or request.httprequest.args.get("db", "") or ""
        with _sse_lock:
            _sse_sessions[sse_id] = {"queue": q, "uid": uid, "db": db}

        # Build message endpoint URL
        base_url = request.httprequest.host_url.rstrip("/")
        msg_url = f"{base_url}/mcp/message?session_id={sse_id}"
        if db:
            msg_url += f"&db={db}"

        cors_headers = self._get_cors_headers()

        def generate():
            try:
                yield f"event: endpoint\ndata: {msg_url}\n\n"
                while True:
                    try:
                        event = q.get(timeout=30)
                        if event is None:  # termination signal
                            break
                        yield event
                    except queue.Empty:
                        yield ": ping\n\n"
            finally:
                with _sse_lock:
                    _sse_sessions.pop(sse_id, None)

        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        headers.update(cors_headers)

        resp = WerkzeugResponse(generate(), status=200, headers=list(headers.items()))
        resp.implicit_sequence_conversion = False
        return resp

    def _handle_sse_message(self):  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements,too-complex
        """HTTP+SSE transport: receive a client→server message and respond via SSE."""
        sse_id = request.httprequest.args.get("session_id", "")
        with _sse_lock:
            session_data = _sse_sessions.get(sse_id)

        if not session_data:
            return self._make_json_response(
                make_error(None, INVALID_REQUEST, "Invalid or expired SSE session."), status=400
            )

        uid = session_data["uid"]
        q: queue.Queue = session_data["queue"]
        env = request.env(user=uid)
        start_time = time.time()
        rpc_id = None
        mcp_method = None
        params = {}
        session = None
        user = env["res.users"].sudo().browse(uid)

        try:
            raw_body = request.httprequest.get_data(as_text=True)
            try:
                rpc_id, mcp_method, params = parse_request(raw_body)
            except JsonRpcError as e:
                q.put(f"event: message\ndata: {json.dumps(e.to_response())}\n\n")
                return self._make_http_response("", status=202)

            handler_key = HANDLERS.get(mcp_method)
            if handler_key is None:
                err = make_error(rpc_id, METHOD_NOT_FOUND, f"Unknown method: {mcp_method}")
                q.put(f"event: message\ndata: {json.dumps(err)}\n\n")
                return self._make_http_response("", status=202)

            if handler_key == "notification":
                return self._make_http_response("", status=202)

            # Validate MCP session for non-initialize requests
            if mcp_method != "initialize":
                session_id = request.httprequest.headers.get("MCP-Session-Id", "")
                if not session_id:
                    err = make_error(rpc_id, INVALID_REQUEST, "Missing MCP-Session-Id header.")
                    q.put(f"event: message\ndata: {json.dumps(err)}\n\n")
                    return self._make_http_response("", status=202)
                session = env["mcp.session"].find_session(session_id)
                if not session:
                    err = make_error(rpc_id, INVALID_REQUEST, "Invalid or expired session.")
                    q.put(f"event: message\ndata: {json.dumps(err)}\n\n")
                    return self._make_http_response("", status=202)
                session.touch()

            rate_limit = int(env["ir.config_parameter"].sudo().get_param("xf_mcp.rate_limit", "60"))
            allowed, _retry_after = check_rate_limit(uid, rate_limit)
            if not allowed:
                err = make_error(rpc_id, INTERNAL_ERROR, "Rate limit exceeded.")
                q.put(f"event: message\ndata: {json.dumps(err)}\n\n")
                return self._make_http_response("", status=202)

            result, new_session = self._dispatch(handler_key, rpc_id, params, env)
            response_body = make_response(rpc_id, result)

            if new_session:
                session = new_session
                # SSE transport: send session ID as a separate event before the response
                q.put(f"event: session\ndata: {new_session.session_id}\n\n")

            is_tool_error = isinstance(result, dict) and result.get("isError", False)
            audit_error_msg = None
            if is_tool_error:
                try:
                    audit_error_msg = result["content"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    audit_error_msg = "Tool execution error"
            self._log_request(
                env=env,
                session=session,
                user=user,
                mcp_method=mcp_method,
                params=params,
                status="error" if is_tool_error else "success",
                error_message=audit_error_msg,
                start_time=start_time,
            )

            q.put(f"event: message\ndata: {json.dumps(response_body)}\n\n")
            return self._make_http_response("", status=202)

        except JsonRpcError as e:
            self._log_request(
                env=env,
                session=session,
                user=user,
                mcp_method=mcp_method,
                params={},
                status="error",
                error_message=str(e),
                start_time=start_time,
            )
            q.put(f"event: message\ndata: {json.dumps(e.to_response())}\n\n")
            return self._make_http_response("", status=202)

        except (ValidationError, AccessError, UserError) as e:
            msg = e.args[0] if e.args else str(e)
            self._log_request(
                env=env,
                session=session,
                user=user,
                mcp_method=mcp_method,
                params=params,
                status="error",
                error_message=msg,
                start_time=start_time,
            )
            q.put(f"event: message\ndata: {json.dumps(make_error(rpc_id, INTERNAL_ERROR, msg))}\n\n")
            return self._make_http_response("", status=202)

        except Exception as e:  # pylint: disable=broad-exception-caught
            _logger.exception("MCP SSE message internal error")
            self._log_request(
                env=env,
                session=session,
                user=user,
                mcp_method=mcp_method,
                params={},
                status="error",
                error_message=str(e),
                start_time=start_time,
            )
            q.put(
                f"event: message\ndata: {json.dumps(make_error(rpc_id, INTERNAL_ERROR, 'Internal server error.'))}\n\n"
            )
            return self._make_http_response("", status=202)

    # -------------------------------------------------------------------------
    # DELETE handler (session termination)
    # -------------------------------------------------------------------------

    def _handle_delete(self):
        session_id = request.httprequest.headers.get("MCP-Session-Id", "")
        if not session_id:
            return self._make_http_response("", status=400)

        session = request.env["mcp.session"].sudo().find_session(session_id)
        if session:
            user_id = session.user_id.id
            session.write({"active": False})
            # Audit log: session termination
            try:
                request.env["mcp.audit.log"].sudo().log_request(
                    {
                        "session_id": session.id,
                        "user_id": user_id,
                        "method": "session/terminate",
                        "response_status": "success",
                        "ip_address": get_client_ip(request),
                        "user_agent": get_user_agent(request),
                        "duration_ms": 0,
                    }
                )
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.exception("Failed to log MCP session termination")
            return self._make_http_response("", status=200)
        return self._make_http_response("", status=404)

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------

    def _cors_preflight(self):
        env = request.env
        allowed_origins = env["ir.config_parameter"].sudo().get_param("xf_mcp.allowed_origins", "")
        origin = request.httprequest.headers.get("Origin", "")

        if allowed_origins:
            origins = [o.strip() for o in allowed_origins.split(",")]
            allow_origin = origin if origin in origins else origins[0]
        else:
            allow_origin = origin or "*"

        return self._make_http_response(
            "",
            status=204,
            headers={
                "Access-Control-Allow-Origin": allow_origin,
                "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": (
                    "Authorization, Content-Type, Accept, MCP-Session-Id, MCP-Protocol-Version"
                ),
                "Access-Control-Expose-Headers": "MCP-Session-Id",
                "Access-Control-Max-Age": "86400",
            },
        )

    def _get_cors_headers(self):
        origin = request.httprequest.headers.get("Origin", "")
        env = request.env
        allowed_origins = env["ir.config_parameter"].sudo().get_param("xf_mcp.allowed_origins", "")

        if allowed_origins:
            origins = [o.strip() for o in allowed_origins.split(",")]
            allow_origin = origin if origin in origins else ""
        else:
            allow_origin = origin or "*"

        return {
            "Access-Control-Allow-Origin": allow_origin,
            "Access-Control-Expose-Headers": "MCP-Session-Id",
        }

    # -------------------------------------------------------------------------
    # Response helpers
    # -------------------------------------------------------------------------

    def _make_json_response(self, body, status=200, headers=None):
        all_headers = {"Content-Type": "application/json"}
        all_headers.update(self._get_cors_headers())
        if headers:
            all_headers.update(headers)
        return self._make_http_response(
            json.dumps(body),
            status=status,
            headers=all_headers,
        )

    @staticmethod
    def _make_http_response(body, status=200, headers=None):
        response = request.make_response(body, headers=list((headers or {}).items()))
        response.status_code = status
        return response

    # -------------------------------------------------------------------------
    # Audit logging
    # -------------------------------------------------------------------------

    def _log_auth_failure(self, env, mcp_method, error_message, start_time=None):
        """Log a failed authentication attempt to the audit trail."""
        try:
            logging_enabled = env["ir.config_parameter"].sudo().get_param("xf_mcp.logging_enabled", "True")
            if not str2bool(logging_enabled):
                return
            duration_ms = (time.time() - start_time) * 1000 if start_time else 0
            env["mcp.audit.log"].sudo().log_request(
                {
                    "user_id": False,
                    "method": mcp_method,
                    "response_status": "denied",
                    "error_message": error_message,
                    "ip_address": get_client_ip(request),
                    "user_agent": get_user_agent(request),
                    "duration_ms": duration_ms,
                }
            )
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("Failed to log MCP auth failure")

    def _log_request(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, env, session, user, mcp_method, params, status, error_message=None, start_time=None
    ):
        """Log MCP request to audit log if logging is enabled.

        Wrapped in a savepoint so a concurrent-update or FK error on the
        audit log INSERT cannot leave the cursor in an aborted state and
        break the main response transaction.
        """
        try:
            logging_enabled = env["ir.config_parameter"].sudo().get_param("xf_mcp.logging_enabled", "True")
            if not str2bool(logging_enabled):
                return

            duration_ms = (time.time() - start_time) * 1000 if start_time else 0

            vals = {
                "session_id": session.id if session else False,
                "user_id": user.id if user else False,
                "method": mcp_method,
                "response_status": status,
                "error_message": error_message,
                "ip_address": get_client_ip(request),
                "user_agent": get_user_agent(request),
                "duration_ms": duration_ms,
            }

            # Extract tool/resource/prompt name from params
            if mcp_method == "tools/call":
                vals["tool_name"] = params.get("name", "")
                vals["request_data"] = json.dumps(params.get("arguments", {}), default=str)
            elif mcp_method == "resources/read":
                vals["resource_uri"] = params.get("uri", "")
            elif mcp_method == "prompts/get":
                vals["prompt_name"] = params.get("name", "")

            with env.cr.savepoint(flush=False):
                env["mcp.audit.log"].log_request(vals)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("Failed to log MCP request")

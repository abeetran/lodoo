# Copyright 2024 XFanis
# License OPL-1 or later (https://www.odoo.com/documentation/master/legal/licenses.html).

from odoo.tests.common import TransactionCase

from ..services.dispatcher import (
    _ALLOWED_CTX_KEYS,
    INVALID_REQUEST,
    PARSE_ERROR,
    JsonRpcError,
    _apply_context,
    handle_ping,
    make_error,
    make_response,
    parse_request,
)


class TestMcpDispatcher(TransactionCase):
    """Tests for MCP dispatcher utilities."""

    def test_make_response_structure(self):
        response = make_response(1, {"key": "value"})
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"], {"key": "value"})

    def test_make_error_structure(self):
        error = make_error(2, -32600, "Invalid request")
        self.assertEqual(error["jsonrpc"], "2.0")
        self.assertEqual(error["id"], 2)
        self.assertEqual(error["error"]["code"], -32600)

    def test_parse_request_valid(self):
        body = '{"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}'
        rpc_id, method, params = parse_request(body)
        self.assertEqual(rpc_id, 1)
        self.assertEqual(method, "ping")
        self.assertEqual(params, {})

    def test_parse_request_invalid_json(self):
        with self.assertRaises(JsonRpcError) as ctx:
            parse_request("{invalid json}")
        self.assertEqual(ctx.exception.code, PARSE_ERROR)

    def test_parse_request_missing_jsonrpc(self):
        with self.assertRaises(JsonRpcError) as ctx:
            parse_request('{"id": 1, "method": "ping"}')
        self.assertEqual(ctx.exception.code, INVALID_REQUEST)

    def test_parse_request_missing_method(self):
        with self.assertRaises(JsonRpcError) as ctx:
            parse_request('{"jsonrpc": "2.0", "id": 1}')
        self.assertEqual(ctx.exception.code, INVALID_REQUEST)

    def test_handle_ping(self):
        self.assertEqual(handle_ping(), {})

    def test_apply_context_lang(self):
        """_apply_context extracts lang and returns cleaned arguments."""
        arguments = {"model": "res.partner", "context": {"lang": "fr_FR", "uid": 1}}
        new_env, cleaned = _apply_context(arguments, self.env)
        # uid is not in whitelist, should be stripped
        self.assertNotIn("uid", new_env.context.get("lang", ""))
        self.assertNotIn("context", cleaned)
        self.assertIn("model", cleaned)
        # lang was whitelisted so env should have it
        self.assertEqual(new_env.context.get("lang"), "fr_FR")

    def test_apply_context_no_context(self):
        """_apply_context is a no-op when no context provided."""
        arguments = {"model": "res.partner"}
        new_env, cleaned = _apply_context(arguments, self.env)
        self.assertEqual(new_env, self.env)
        self.assertEqual(cleaned, arguments)

    def test_allowed_ctx_keys(self):
        """All expected context keys are in the whitelist."""
        self.assertIn("lang", _ALLOWED_CTX_KEYS)
        self.assertIn("tz", _ALLOWED_CTX_KEYS)
        self.assertIn("allowed_company_ids", _ALLOWED_CTX_KEYS)

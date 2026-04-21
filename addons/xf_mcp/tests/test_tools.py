# Copyright 2024 XFanis
# License OPL-1 or later (https://www.odoo.com/documentation/master/legal/licenses.html).

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestMcpTools(TransactionCase):
    """Tests for MCP tool execution."""

    def setUp(self):
        super().setUp()
        self.tool = self.env["mcp.tool"].sudo()

    def test_blocked_models_property(self):
        """_blocked_models returns a frozenset with known entries."""
        blocked = self.tool._blocked_models
        self.assertIsInstance(blocked, frozenset)
        self.assertIn("ir.config_parameter", blocked)
        self.assertIn("mcp.session", blocked)
        self.assertIn("res.users.apikeys", blocked)

    def test_blocked_methods_property(self):
        """_blocked_methods does not contain messaging methods (bridge module concern)."""
        blocked = self.tool._blocked_methods
        self.assertIsInstance(blocked, frozenset)
        self.assertIn("sudo", blocked)
        self.assertIn("create", blocked)
        self.assertNotIn("message_post", blocked)
        self.assertNotIn("import_data", blocked)

    def test_check_model_allowed_blocked(self):
        """Accessing blocked model raises UserError."""
        with self.assertRaises(UserError):
            self.tool._check_model_allowed("ir.config_parameter", self.env)

    def test_check_model_allowed_nonexistent(self):
        """Accessing non-existent model raises UserError."""
        with self.assertRaises(UserError):
            self.tool._check_model_allowed("nonexistent.model.xyz", self.env)

    def test_check_model_allowed_valid(self):
        """res.partner is accessible and returns None (no override)."""
        result = self.tool._check_model_allowed("res.partner", self.env)
        self.assertIsNone(result)

    def test_execute_search_basic(self):
        """search tool returns records."""
        result = self.tool._execute_search(self.env, {"model": "res.partner", "limit": 5})
        self.assertIn("records", result)
        self.assertIn("count", result)
        self.assertIn("total", result)

    def test_execute_count(self):
        """count tool returns integer."""
        result = self.tool._execute_count(self.env, {"model": "res.partner"})
        self.assertIn("count", result)
        self.assertIsInstance(result["count"], int)

    def test_execute_search_blocked_model(self):
        """search on blocked model raises UserError."""
        with self.assertRaises(UserError):
            self.tool._execute_search(self.env, {"model": "ir.config_parameter"})

    def test_execute_list_companies(self):
        """list_companies returns current company and list."""
        result = self.tool._execute_list_companies(self.env, {})
        self.assertIn("current_company_id", result)
        self.assertIn("companies", result)
        self.assertIsInstance(result["companies"], list)

    def test_get_methods_on_base(self):
        """get_methods returns public methods list."""
        methods = self.env["res.partner"].get_methods()
        self.assertIsInstance(methods, list)
        self.assertIn("search", methods)
        self.assertIn("read", methods)
        # Private methods not included
        self.assertNotIn("_check_recursion", methods)

    def test_validate_domain_too_large(self):
        """Domain with >50 clauses raises UserError."""
        domain = [("id", ">", 0)] * 51
        with self.assertRaises(UserError):
            self.tool._validate_domain(domain)

    def test_check_method_allowed_private(self):
        """Private method raises UserError."""
        with self.assertRaises(UserError):
            self.tool._check_method_allowed("_check_recursion")

    def test_check_method_allowed_blocked(self):
        """Blocked method raises UserError."""
        with self.assertRaises(UserError):
            self.tool._check_method_allowed("sudo")

    def test_format_records_many2one(self):
        """_format_records serializes Many2one as dict."""
        partner = self.env["res.partner"].sudo().search([("company_id", "!=", False)], limit=1)
        if partner:
            result = self.tool._format_records(partner, ["company_id"])
            self.assertIsInstance(result, list)
            m2o = result[0].get("company_id")
            if m2o:
                self.assertIn("id", m2o)
                self.assertIn("display_name", m2o)

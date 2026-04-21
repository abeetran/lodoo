# Copyright 2024 XFanis
# License OPL-1 or later (https://www.odoo.com/documentation/master/legal/licenses.html).

import json

from odoo.tests.common import TransactionCase


class TestMcpResources(TransactionCase):
    """Tests for MCP resource resolvers."""

    def setUp(self):
        super().setUp()
        self.resource_model = self.env["mcp.resource"].sudo()

    def test_resolve_system_info(self):
        """odoo://system/info returns valid JSON with expected keys."""
        result = self.resource_model.resolve_uri("odoo://system/info")
        self.assertIsNotNone(result)
        text = result["contents"][0]["text"]
        data = json.loads(text)
        self.assertIn("odoo_version", data)
        self.assertIn("database", data)
        self.assertIn("company", data)

    def test_resolve_system_prompt(self):
        """odoo://system/prompt returns text content."""
        result = self.resource_model.resolve_uri("odoo://system/prompt")
        self.assertIsNotNone(result)
        self.assertEqual(result["contents"][0]["mimeType"], "text/plain")
        self.assertTrue(result["contents"][0]["text"])

    def test_resolve_user_me(self):
        """odoo://user/me returns current user info."""
        result = self.resource_model.resolve_uri("odoo://user/me")
        self.assertIsNotNone(result)
        data = json.loads(result["contents"][0]["text"])
        self.assertIn("id", data)
        self.assertIn("lang", data)
        self.assertIn("company", data)

    def test_resolve_model_schema(self):
        """odoo://model/res.partner/schema returns field definitions."""
        result = self.resource_model.resolve_uri("odoo://model/res.partner/schema")
        self.assertIsNotNone(result)
        data = json.loads(result["contents"][0]["text"])
        self.assertIn("fields", data)
        self.assertIn("name", data["fields"])

    def test_resolve_model_access(self):
        """odoo://model/res.partner/access returns permission info."""
        result = self.resource_model.resolve_uri("odoo://model/res.partner/access")
        self.assertIsNotNone(result)
        data = json.loads(result["contents"][0]["text"])
        self.assertIn("odoo_permissions", data)
        self.assertIn("effective", data)

    def test_resolve_nonexistent_uri(self):
        """Unknown URI returns None."""
        result = self.resource_model.resolve_uri("odoo://nonexistent/resource")
        self.assertIsNone(result)

    def test_match_uri_template(self):
        """URI template matching extracts parameters correctly."""
        resource = self.resource_model.search([("uri_pattern", "=", "odoo://model/{model}/schema")], limit=1)
        if resource:
            params = resource._match_uri("odoo://model/sale.order/schema")
            self.assertEqual(params, {"model": "sale.order"})
            self.assertIsNone(resource._match_uri("odoo://model/sale.order/other"))

    def test_resolve_record_fields(self):
        """odoo://record/{model}/{id}/fields/{fields} returns only specified fields."""
        partner = self.env["res.partner"].sudo().search([], limit=1)
        if partner:
            uri = f"odoo://record/res.partner/{partner.id}/fields/name,email"
            result = self.resource_model.resolve_uri(uri)
            self.assertIsNotNone(result)
            data = json.loads(result["contents"][0]["text"])
            self.assertIn("name", data["data"])
            self.assertNotIn("phone", data["data"])

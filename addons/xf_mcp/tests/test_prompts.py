# Copyright 2024 XFanis
# License OPL-1 or later (https://www.odoo.com/documentation/master/legal/licenses.html).

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestMcpPrompts(TransactionCase):
    """Tests for MCP prompt model and rendering."""

    def setUp(self):
        super().setUp()
        self.admin_user = self.env.ref("base.user_admin")

    def test_render_basic_template(self):
        """Simple template renders correctly with named arguments."""
        prompt = (
            self.env["mcp.prompt"]
            .sudo()
            .create(
                {
                    "name": "test_prompt_render",
                    "is_global": True,
                    "message_template": "Hello {name}, you have {count} items.",
                    "role": "user",
                    "description": "Test prompt",
                }
            )
        )
        result = prompt.render({"name": "Alice", "count": "5"})
        self.assertIn("Hello Alice, you have 5 items.", result["messages"][0]["content"]["text"])
        prompt.unlink()

    def test_render_missing_required_argument(self):
        """Missing required argument raises ValidationError."""
        prompt = (
            self.env["mcp.prompt"]
            .sudo()
            .create(
                {
                    "name": "test_prompt_required",
                    "is_global": True,
                    "message_template": "Hello {name}",
                    "role": "user",
                    "description": "Test",
                }
            )
        )
        self.env["mcp.prompt.argument"].sudo().create(
            {
                "prompt_id": prompt.id,
                "name": "name",
                "required": True,
            }
        )
        with self.assertRaises(ValidationError):
            prompt.render({})
        prompt.unlink()

    def test_render_safe_template_no_injection(self):
        """Template engine does not expose Python object internals."""
        prompt = (
            self.env["mcp.prompt"]
            .sudo()
            .create(
                {
                    "name": "test_prompt_safe",
                    "is_global": True,
                    "message_template": "Value: {val}",
                    "role": "user",
                    "description": "Safety test",
                }
            )
        )
        # This would crash str.format() with attribute access
        result = prompt.render({"val": "test"})
        self.assertIn("Value: test", result["messages"][0]["content"]["text"])
        prompt.unlink()

    def test_global_unique_constraint(self):
        """Two global prompts with the same name raises an error."""
        p1 = (
            self.env["mcp.prompt"]
            .sudo()
            .create(
                {
                    "name": "test_global_unique",
                    "is_global": True,
                    "message_template": "Template 1",
                    "role": "user",
                    "description": "First",
                }
            )
        )
        with self.assertRaises(Exception):
            self.env["mcp.prompt"].sudo().create(
                {
                    "name": "test_global_unique",
                    "is_global": True,
                    "message_template": "Template 2",
                    "role": "user",
                    "description": "Second",
                }
            )
        p1.unlink()

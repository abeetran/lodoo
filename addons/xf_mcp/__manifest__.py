{
    "name": "MCP Server",
    "version": "17.0.1.0.0",
    "category": "Technical",
    "author": "XFanis",
    "support": "xfanis.dev@gmail.com",
    "website": "https://odoo-addons.xfanis.dev/apps/modules/19.0/xf_mcp",
    "live_test_url": "https://odoo-addons.xfanis.dev/apps/modules/19.0/xf_mcp?request_demo",
    "license": "OPL-1",
    "price": 1,
    "summary": """
    Connect AI assistants like Claude, Codex, ChatGPT, Cursor, and VS Code to your Odoo instance
    via Model Context Protocol.
    Expose Odoo data and operations securely with native ACL, audit trail, rate limiting,
    IP filtering, and session management.
    | MCP server
    | Model Context Protocol
    | AI integration
    | Odoo AI
    | Claude Odoo
    | Cursor Odoo
    | Codex Odoo
    | ChatGPT Odoo
    | VS Code Odoo
    | AI assistant
    | Odoo MCP
    | AI agent
    | Streamable HTTP
    | MCP tools
    | MCP resources
    | MCP prompts
    | Ollama Odoo
    | LM Studio Odoo
    | local AI Odoo
    """,
    "description": """
MCP Server for Odoo

This module turns your Odoo instance into a fully functional Model Context Protocol (MCP) server,
allowing AI assistants such as Claude, Cursor, GitHub Copilot, and VS Code AI extensions to
interact directly with your ERP data and business logic.

Unlike external proxy solutions, this is a native Odoo implementation — no middleware, no extra
services, no Python dependencies. The MCP endpoint runs inside Odoo over Streamable HTTP transport
with JSON-RPC 2.0, making it compatible with any MCP-compatible AI client or IDE plugin.

Connect Claude Desktop or Claude.ai to Odoo and let it search records, read model schemas, create
or update data, and execute business operations — all within the permissions your Odoo access
control rules already define. The same applies to ChatGPT (via OpenAI's MCP support), Codex,
Cursor AI, Windsurf, Cline, Continue.dev, or any other AI coding assistant that supports the MCP protocol.

KEY FEATURES:

Native MCP protocol — Streamable HTTP transport with JSON-RPC 2.0, compatible with Claude,
ChatGPT, Codex, Cursor, VS Code Copilot, Windsurf, Cline, and other MCP clients.

Flexible authentication — Bearer token (Odoo API key) via Authorization header, so you can
connect any AI tool securely without exposing user credentials.

Configurable MCP tools — enable or disable individual operations (search, read, create, write,
delete, count) per model, giving you fine-grained control over what AI agents can do.

MCP resources — expose system info, model schemas, and record data as structured resources that
AI assistants can browse and reason about.

Custom MCP prompts — admins define global prompt templates; users can also create personal
prompts to guide AI behavior for specific workflows.

Odoo-native access control — the MCP server respects your existing Odoo ACL rules as the primary
authority. AI assistants can only see and modify what the authenticated user is allowed to access
in the browser.

Per-model MCP overrides — apply additional restrictions on top of Odoo ACL for sensitive models,
without changing your existing security configuration.

Full audit trail — every AI request is logged with configurable retention, giving you complete
visibility into what AI agents read or changed.

IP filtering — define allow-lists or deny-lists to restrict which networks or machines can reach
the MCP endpoint.

Rate limiting — protect your Odoo server from excessive AI agent activity with per-user request
rate limits.

Session management — MCP sessions have a configurable TTL, automatically expiring idle AI
connections to keep the system clean.

USE CASES:

Odoo AI integration for developers using Cursor or VS Code to build and debug Odoo modules.
Claude Desktop connected to live Odoo data for business analysis and reporting.
AI agent automation for routine ERP tasks such as creating records, updating statuses, or
running searches across multiple models.
Secure AI access to Odoo for non-technical users through MCP-compatible chat interfaces.
Private on-premise AI workflows using local models via Ollama or LM Studio with full data sovereignty.
    """,
    "depends": [
        "base",
    ],
    "data": [
        "security/mcp_security.xml",
        "security/ir.model.access.csv",
        "data/mcp_defaults.xml",
        "data/mcp_tools_data.xml",
        "data/mcp_resources_data.xml",
        "views/mcp_tool_views.xml",
        "views/mcp_resource_views.xml",
        "views/mcp_prompt_views.xml",
        "views/mcp_access_views.xml",
        "views/mcp_audit_log_views.xml",
        "views/mcp_session_views.xml",
        "views/res_config_settings_views.xml",
        "views/menu.xml",
    ],
    "images": ["static/description/cover_image.png"],
    "post_load": "post_load",
    "auto_install": False,
    "application": True,
    'installable': True,
}

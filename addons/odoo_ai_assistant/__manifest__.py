{
    "name": "AI Assistant (MCP)",
    "version": "1.0",
    "summary": "AI Assistant integrated with MCP Server",
    "author": "Custom",
    "category": "Productivity",
    "depends": ["base", "web", "mail"],
    "assets": {
        "web.assets_backend": [
            "odoo_ai_assistant/static/src/components/ai_chat/ai_chat.scss",
            "odoo_ai_assistant/static/src/components/ai_chat/ai_chat.xml",
            "odoo_ai_assistant/static/src/components/ai_chat/ai_chat.js",
        ]
    },
    "data": [
        "security/ir.model.access.csv",
        "views/ai_chat_view.xml",
    ],
    "installable": True,
    "application": True
}

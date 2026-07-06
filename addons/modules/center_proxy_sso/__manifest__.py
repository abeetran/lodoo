{
    "name": "Center Proxy SSO",
    "version": "17.0.1.0.0",
    "category": "Technical",
    "summary": "SSO launch token (one-time JWT) + URL prefix cho iframe qua center manager",
    "license": "LGPL-3",
    "depends": ["web", "web_session_fix"],
    "installable": True,
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "views/login_center_only.xml",
        "views/login_layout_inherit.xml",
    ],
}

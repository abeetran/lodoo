# -*- coding: utf-8 -*-
{
    "name": "Authentik Login Button",
    "version": "17.0.1.0.0",
    "category": "Authentication",
    "summary": "Trang /web/login chỉ có nút chuyển sang Authentik (OIDC qua auth_authentik_sso)",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["base", "web", "auth_authentik_sso"],
    "data": [
        "views/login_template.xml",
        "views/odoo_login.xml",
    ],
    "installable": True,
    "application": False,
}

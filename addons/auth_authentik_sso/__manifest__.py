# -*- coding: utf-8 -*-
{
    "name": "Authentik SSO Login (OIDC)",
    "version": "17.0.1.0.0",
    "category": "Authentication",
    "summary": "Login to Odoo using Authentik via OpenID Connect",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/web_login_template.xml",
    ],
    "installable": True,
    "application": True,
}

# -*- coding: utf-8 -*-
{
    "name": "Authentik Login From Odoo",
    "version": "17.0.1.0.0",
    "category": "AuthentikLogin",
    "summary": "Login to Odoo using Authentik via OpenID Connect",
    "author": "Custom",
    "depends": ["base", "web"],
    "data": [
        "views/login_template.xml",
    ],
    "installable": True,
    "application": True,
}

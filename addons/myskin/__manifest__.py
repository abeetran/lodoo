{
    "name": "My Skin",
    "version": "17.0.1.0.0",
    "category": "Themes",
    "author": "Your Company",
    "license": "LGPL-3",
    "depends": [
        "web",
        "auth_signup",
        "auth_authentik_sso",
    ],
    "data": [
        "views/assets.xml",
        "views/authentik_login_page.xml",
        "views/authentik_login_only.xml",
        "views/odoo_login.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "myskin/static/src/css/backend.css",
            "myskin/static/src/js/*.js",
            # "myskin/static/src/js/hide_odoo_account.js",
            # "myskin/static/src/js/default_home.js",
        ],
        "web.assets_frontend": [
            "myskin/static/src/css/login.css",
        ],
        'web.assets_common': [
            'myskin/static/src/css/login.css',
        ],
    },
    "installable": True,
    "application": True,
}
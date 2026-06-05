{
    "name": "My Skin",
    "version": "17.0.1.0.0",
    "category": "Themes",
    "author": "Your Company",
    "license": "LGPL-3",
    "depends": [
        "web",
    ],
    "data": [
        # "views/login_templates.xml",
        # "views/assets.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "myskin/static/src/css/backend.css",
            "myskin/static/src/js/backend.js",
            "myskin/static/src/js/hide_odoo_account.js",
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
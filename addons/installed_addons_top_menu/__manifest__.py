{
    "name": "Installed Addons Top Menu",
    "version": "17.0.1.0.0",
    "category": "Tools",
    "summary": "Horizontal Odoo application menu",

    "depends": [
        "web",
    ],

    "data": [],

    "assets": {
        "web.assets_backend": [
            "installed_addons_top_menu/static/src/js/installed_addons_top_menu.js",
            "installed_addons_top_menu/static/src/xml/installed_addons_top_menu.xml",
            "installed_addons_top_menu/static/src/scss/installed_addons_top_menu.scss",
        ],
    },

    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
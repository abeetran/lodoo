{
    "name": "Custom Addons Top Menu",
    "version": "17.0.1.0.11",
    "category": "Web",
    "summary": "Custom top navigation menu",
    "description": """
        Installed Addons Top Menu
        =========================
        Adds a custom navigation menu to the Odoo top navbar.
        """,
    "author": "ozawa",
    "website": "",
    "license": "LGPL-3",

    "depends": [
        "web",
        "base",
        "auth_signup",
        "sale",
        "sale_management",
        "account",
        "stock",
        "purchase",
        "crm",
        "mrp",
        "crall_material",
    ],

    "data": [
        "security/ir.model.access.csv",
        "data/kitchen_plan_sequence.xml",
        "data/menu_item_data.xml",
        "views/client_management_views.xml",
        "views/client_contract_views.xml",
        "views/menu_item_views.xml",
        "views/menu_views.xml",
        "views/res_users_views.xml",
        "views/material_views.xml",
        "views/kitchen_plan_views.xml",
        "views/production_process_views.xml",
        "views/sale_order_views.xml",
        "views/daily_order_views.xml",
        "views/warehouse_views.xml",
        "views/web_login_views.xml",
    ],

    "assets": {
        "web.assets_backend": [
            "set_top_menu/static/src/js/custom_navbar.js",
            "set_top_menu/static/src/js/dish_stage_list.js",
            "set_top_menu/static/src/xml/custom_navbar.xml",
            "set_top_menu/static/src/xml/dish_stage_list.xml",
            "set_top_menu/static/src/scss/custom_navbar.scss",
            "set_top_menu/static/src/scss/dish_stage_list.scss",
        ],
    },

    "installable": True,
    "application": True,
}

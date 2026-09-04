{
    "name": "Craw Material Supplier Sync",
    "version": "17.0.1.0.6",
    "category": "Inventory",
    "summary": "Import standard foods from the HanoiCheck supplier API",
    "depends": ["product", "sale", "base_setup"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/product_template_views.xml",
        "views/sync_wizard_views.xml",
        "views/crall_material_menus.xml",
    ],
    "external_dependencies": {"python": ["requests"]},
    "installable": True,
    "application": True,
}
{
    "name": "Chatwoot CRM Integration",
    "version": "17.0.1.0.0",
    "summary": "Sync Odoo CRM leads with Chatwoot contacts and conversations",
    "author": "Custom",
    "category": "Sales/CRM",
    "license": "LGPL-3",
    "depends": ["crm", "mail"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/crm_lead_views.xml",
    ],
    "installable": True,
    "application": True,
}

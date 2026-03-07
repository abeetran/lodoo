from odoo import fields, models

class ResUsers(models.Model):
    _inherit = "res.users"

    authentik_sub = fields.Char(index=True, copy=False)

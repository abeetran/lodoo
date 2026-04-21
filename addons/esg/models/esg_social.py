from odoo import models, fields, api

class ESGSocial(models.Model):
    _name = "esg.social"
    _description = "Social KPI"

    employee_count = fields.Integer()
    training_hours = fields.Float()
    accident_count = fields.Integer()

    diversity_ratio = fields.Float()
from odoo import models, fields, api

class ESGEnvironment(models.Model):
    _name = "esg.environment"
    _description = "Environmental Data"

    name = fields.Char()
    date = fields.Date()

    electricity_kwh = fields.Float()
    water_m3 = fields.Float()
    fuel_liter = fields.Float()

    co2_equivalent = fields.Float(compute="_compute_co2")

    def _compute_co2(self):
        for r in self:
            r.co2_equivalent = (
                r.electricity_kwh * 0.5 +
                r.fuel_liter * 2.3
            )
from odoo import models, fields, api

class ESGReport(models.Model):
    _name = "esg.report"
    _description = "ESG Report"
    _inherit = ["mail.thread"]

    name = fields.Char(string="Report Name", required=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    date_from = fields.Date()
    date_to = fields.Date()

    # tổng hợp KPI
    co2_emission = fields.Float()
    energy_usage = fields.Float()
    water_usage = fields.Float()

    social_score = fields.Float()
    governance_score = fields.Float()

    total_score = fields.Float(compute="_compute_total")

    @api.depends("co2_emission", "social_score", "governance_score")
    def _compute_total(self):
        for rec in self:
            rec.total_score = (
                rec.social_score +
                rec.governance_score -
                rec.co2_emission * 0.1
            )
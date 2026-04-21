from odoo import models, fields, api

class ESGGovernance(models.Model):
    _name = "esg.governance"
    _description = "Governance KPI"

    audit_score = fields.Float()
    compliance_rate = fields.Float()
    policy_violations = fields.Integer()
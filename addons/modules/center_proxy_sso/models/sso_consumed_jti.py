# -*- coding: utf-8 -*-
from odoo import fields, models


class CenterSsoConsumedJti(models.Model):
    _name = "center.sso.consumed.jti"
    _description = "One-time SSO launch token (jti đã dùng)"
    _order = "consumed_at desc"

    jti = fields.Char(required=True, index=True)
    email = fields.Char()
    tenant_id = fields.Char(index=True)
    consumed_at = fields.Datetime(default=fields.Datetime.now, required=True)

    _sql_constraints = [
        ("jti_unique", "unique(jti)", "JWT jti đã được sử dụng"),
    ]

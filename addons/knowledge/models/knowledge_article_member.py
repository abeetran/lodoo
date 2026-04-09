# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class KnowledgeArticleMember(models.Model):
    _name = 'knowledge.article.member'
    _description = 'Thành viên bài viết Knowledge'
    _rec_name = 'partner_id'

    article_id = fields.Many2one(
        'knowledge.article',
        string='Bài viết',
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Thành viên',
        required=True,
        ondelete='cascade',
        index=True,
    )
    permission = fields.Selection([
        ('read', 'Chỉ xem'),
        ('write', 'Chỉnh sửa'),
    ], string='Quyền', default='read', required=True)

    article_name = fields.Char(
        related='article_id.name',
        string='Tên bài viết',
        readonly=True,
    )
    article_type = fields.Selection(
        related='article_id.article_type',
        string='Loại',
        readonly=True,
    )

    _sql_constraints = [
        ('unique_member', 'UNIQUE(article_id, partner_id)',
         'Thành viên này đã được thêm vào bài viết rồi!'),
    ]

    def name_get(self):
        return [(rec.id, '%s - %s' % (rec.partner_id.name, rec.article_id.name)) for rec in self]

# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class KnowledgeInviteWizard(models.TransientModel):
    _name = 'knowledge.invite.wizard'
    _description = 'Mời thành viên vào bài viết'

    article_id = fields.Many2one(
        'knowledge.article',
        string='Bài viết',
        required=True,
        readonly=True,
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Thành viên được mời',
        required=True,
    )
    permission = fields.Selection([
        ('read', 'Chỉ xem'),
        ('write', 'Chỉnh sửa'),
    ], string='Quyền', default='write', required=True)
    send_mail = fields.Boolean(string='Gửi email thông báo', default=True)

    def action_invite(self):
        """Thêm thành viên vào bài viết."""
        self.ensure_one()
        article = self.article_id
        existing_partners = article.article_member_ids.mapped('partner_id')
        new_partners = self.partner_ids - existing_partners

        member_vals = []
        for partner in new_partners:
            member_vals.append({
                'article_id': article.id,
                'partner_id': partner.id,
                'permission': self.permission,
            })
        if member_vals:
            self.env['knowledge.article.member'].create(member_vals)

        # Gửi thông báo trong chatter
        if self.send_mail and new_partners:
            partner_names = ', '.join(new_partners.mapped('name'))
            perm_label = dict(self._fields['permission'].selection).get(self.permission, '')
            article.message_post(
                body=_('<b>Đã mời thành viên:</b> %s với quyền <b>%s</b>') % (partner_names, perm_label),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            # Gửi email mời
            if self.send_mail:
                template_vals = {
                    'article_name': article.name,
                    'article_url': '/web#model=knowledge.article&id=%d&view_type=form' % article.id,
                    'invited_by': self.env.user.name,
                    'permission': perm_label,
                }
                for partner in new_partners:
                    try:
                        article.message_notify(
                            partner_ids=partner.ids,
                            subject=_('Bạn được mời vào bài viết: %s') % article.name,
                            body=_(
                                '<p>Xin chào <b>%s</b>,</p>'
                                '<p><b>%s</b> đã mời bạn vào bài viết <b>%s</b> với quyền <b>%s</b>.</p>'
                                '<p><a href="%s">Nhấn vào đây để xem bài viết</a></p>'
                            ) % (partner.name, self.env.user.name, article.name, perm_label,
                                 template_vals['article_url']),
                        )
                    except Exception:
                        pass

        # Cập nhật article_type thành shared nếu đang là private
        if article.article_type == 'private' and new_partners:
            article.article_type = 'shared'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mời thành công'),
                'message': _('Đã thêm %d thành viên vào bài viết.') % len(new_partners),
                'type': 'success',
                'sticky': False,
            }
        }

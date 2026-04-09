# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
from odoo.exceptions import AccessError, UserError
import json


class KnowledgeArticle(models.Model):
    _name = 'knowledge.article'
    _description = 'Knowledge Article'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'
    _parent_name = 'parent_id'
    _parent_store = True
    _rec_name = 'name'
    is_template = fields.Boolean(
    string='Là mẫu bài viết',
    default=False,
    tracking=True,
    help='Đánh dấu bài viết này là mẫu để tái sử dụng ở nơi khác.',
    )
    template_description = fields.Char(
    string='Mô tả mẫu',
    help='Mô tả ngắn gọn mẫu này dùng để làm gì.',
    )
    # -------------------------------------------------------------------------
    # FIELDS CƠ BẢN
    # -------------------------------------------------------------------------
    name = fields.Char(
        string='Tiêu đề',
        required=True,
        tracking=True,
        default='Bài viết không tên'
    )
    sequence = fields.Integer(string='Thứ tự', default=10)
    icon = fields.Char(
        string='Biểu tượng',
        help='Nhập 1 emoji (vd: 🚀 📚 💡 📝)',
        default='📄'
    )
    cover_image = fields.Image(string='Ảnh bìa', max_width=1920, max_height=400)
    body = fields.Html(
        string='Nội dung',
        sanitize=False,
        translate=False,
    )
    active = fields.Boolean(default=True, tracking=True)

    # -------------------------------------------------------------------------
    # KHÔNG GIAN LÀM VIỆC
    # -------------------------------------------------------------------------
    article_type = fields.Selection([
        ('workspace', 'Workspace'),
        ('shared', 'Shared'),
        ('private', 'Private'),
    ], string='Không gian', default='workspace', required=True, tracking=True,
       index=True)

    # -------------------------------------------------------------------------
    # CẤU TRÚC CÂY PHÂN CẤP
    # -------------------------------------------------------------------------
    parent_id = fields.Many2one(
        'knowledge.article',
        string='Bài viết cha',
        index=True,
        ondelete='cascade',
        tracking=True,
    )
    child_ids = fields.One2many(
        'knowledge.article', 'parent_id',
        string='Bài viết con'
    )
    child_count = fields.Integer(
        string='Số bài con',
        compute='_compute_child_count',
        store=True,
    )
    parent_path = fields.Char(index=True, unaccent=False)

    # Breadcrumb (danh sách tổ tiên)
    full_name = fields.Char(
        string='Đường dẫn đầy đủ',
        compute='_compute_full_name',
        store=False,
    )

    # -------------------------------------------------------------------------
    # NGƯỜI DÙNG & QUYỀN
    # -------------------------------------------------------------------------
    owner_id = fields.Many2one(
        'res.users',
        string='Chủ sở hữu',
        default=lambda self: self.env.user,
        tracking=True,
        index=True,
    )
    last_edition_uid = fields.Many2one(
        'res.users',
        string='Chỉnh sửa lần cuối bởi',
        default=lambda self: self.env.user,
        ondelete='set null',
    )
    last_edition_date = fields.Datetime(
        string='Thời gian chỉnh sửa cuối',
        default=fields.Datetime.now,
    )

    article_member_ids = fields.One2many(
        'knowledge.article.member',
        'article_id',
        string='Thành viên',
    )
    member_count = fields.Integer(
        string='Thành viên',
        compute='_compute_member_count',
        store=True,
    )

    # -------------------------------------------------------------------------
    # YÊU THÍCH
    # -------------------------------------------------------------------------
    favorite_user_ids = fields.Many2many(
        'res.users',
        'knowledge_article_favorite_rel',
        'article_id', 'user_id',
        string='Người yêu thích',
    )
    is_favorite = fields.Boolean(
        string='Yêu thích',
        compute='_compute_is_favorite',
        inverse='_inverse_is_favorite',
    )
    favorite_count = fields.Integer(
        string='Số lượt thích',
        compute='_compute_favorite_count',
        store=True,
    )

    # -------------------------------------------------------------------------
    # KHÓA BÀI VIẾT
    # -------------------------------------------------------------------------
    is_locked = fields.Boolean(
        string='Đã khóa',
        default=False,
        tracking=True,
        help='Khi khóa, chỉ chủ sở hữu hoặc quản trị viên mới có thể chỉnh sửa.',
    )

    # -------------------------------------------------------------------------
    # THỐNG KÊ
    # -------------------------------------------------------------------------
    visits = fields.Integer(string='Lượt xem', default=0, readonly=True)

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('child_ids')
    def _compute_child_count(self):
        for article in self:
            article.child_count = len(article.child_ids)

    @api.depends('article_member_ids')
    def _compute_member_count(self):
        for article in self:
            article.member_count = len(article.article_member_ids)

    @api.depends('favorite_user_ids')
    def _compute_is_favorite(self):
        for article in self:
            article.is_favorite = self.env.user in article.favorite_user_ids

    def _inverse_is_favorite(self):
        for article in self:
            if article.is_favorite:
                article.sudo().favorite_user_ids = [(4, self.env.user.id)]
            else:
                article.sudo().favorite_user_ids = [(3, self.env.user.id)]

    @api.depends('favorite_user_ids')
    def _compute_favorite_count(self):
        for article in self:
            article.favorite_count = len(article.favorite_user_ids)

    @api.depends('name', 'parent_id', 'parent_id.full_name')
    def _compute_full_name(self):
        for article in self:
            if article.parent_id:
                article.full_name = '%s / %s' % (article.parent_id.full_name, article.name)
            else:
                article.full_name = article.name

    # =========================================================================
    # CRUD OVERRIDES
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('owner_id'):
                vals['owner_id'] = self.env.user.id
        articles = super().create(vals_list)
        # Tự động thêm người tạo vào member của bài Shared
        for article in articles:
            if article.article_type == 'shared':
                self.env['knowledge.article.member'].sudo().create({
                    'article_id': article.id,
                    'partner_id': self.env.user.partner_id.id,
                    'permission': 'write',
                })
        return articles

    def write(self, vals):
        if 'body' in vals or 'name' in vals:
            vals['last_edition_uid'] = self.env.user.id
            vals['last_edition_date'] = fields.Datetime.now()
        # Kiểm tra khóa bài
        for article in self:
            if article.is_locked and 'body' in vals:
                if article.owner_id != self.env.user and \
                        not self.env.user.has_group('base.group_erp_manager'):
                    raise UserError(_(
                        'Bài viết "%s" đang bị khóa. Chỉ chủ sở hữu hoặc quản trị viên mới có thể chỉnh sửa.'
                    ) % article.name)
        return super().write(vals)

    # =========================================================================
    # ACTIONS / BUTTONS
    # =========================================================================
    # Bảo mật được xử lý qua Record Rules trong security/knowledge_security.xml

    def action_toggle_favorite(self):
        """Toggle yêu thích cho bài viết hiện tại."""
        self.ensure_one()
        self.is_favorite = not self.is_favorite
        return True

    def action_toggle_lock(self):
        """Khóa / mở khóa bài viết."""
        self.ensure_one()
        if self.owner_id != self.env.user and \
                not self.env.user.has_group('base.group_erp_manager'):
            raise UserError(_('Chỉ chủ sở hữu mới có thể khóa/mở khóa bài viết này.'))
        self.is_locked = not self.is_locked
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Thành công'),
                'message': _('Bài viết đã được %s.') % (_('khóa') if self.is_locked else _('mở khóa')),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_archive(self):
        """Lưu trữ bài viết (và tất cả bài con)."""
        self.ensure_one()
        self.with_context(active_test=False).child_ids.action_archive()
        self.active = False

    def action_unarchive(self):
        """Khôi phục bài viết."""
        self.ensure_one()
        self.active = True

    def action_open_form(self):
        """Mở bài viết dạng form đầy đủ."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'knowledge.article',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_child(self):
        """Tạo bài viết con mới."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bài viết mới'),
            'res_model': 'knowledge.article',
            'view_mode': 'form',
            'context': {
                'default_parent_id': self.id,
                'default_article_type': self.article_type,
            },
            'target': 'current',
        }

    def action_invite_members(self):
        """Mở wizard mời thành viên."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Mời thành viên'),
            'res_model': 'knowledge.invite.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_article_id': self.id},
        }

    def action_view_members(self):
        """Xem danh sách thành viên."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Thành viên - %s') % self.name,
            'res_model': 'knowledge.article.member',
            'view_mode': 'tree,form',
            'domain': [('article_id', '=', self.id)],
            'context': {'default_article_id': self.id},
        }

    def action_clone(self):
        """Nhân bản bài viết."""
        self.ensure_one()
        new_article = self.copy({
            'name': _('%s (Bản sao)') % self.name,
            'parent_id': self.parent_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'knowledge.article',
            'res_id': new_article.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_track_view(self):
        """Tăng lượt xem."""
        self.ensure_one()
        self.sudo().visits += 1
        return True

    def get_breadcrumbs(self):
        """Trả về danh sách breadcrumb từ gốc đến bài hiện tại."""
        self.ensure_one()
        breadcrumbs = []
        article = self
        while article:
            breadcrumbs.insert(0, {'id': article.id, 'name': article.name, 'icon': article.icon or '📄'})
            article = article.parent_id
        return breadcrumbs

    @api.model
    def get_tree_data(self):
        """Trả về toàn bộ cây bài viết cho sidebar JS."""
        articles = self.search([('parent_id', '=', False)], order='sequence, id')
        return [self._article_to_dict(a) for a in articles]

    def _article_to_dict(self, article):
        children = []
        for child in article.child_ids.sorted(key=lambda r: (r.sequence, r.id)):
            children.append(self._article_to_dict(child))
        return {
            'id': article.id,
            'name': article.name,
            'icon': article.icon or '📄',
            'is_favorite': article.is_favorite,
            'article_type': article.article_type,
            'child_count': article.child_count,
            'children': children,
        }

    @api.model
    def get_recent_articles(self, limit=10):
        """Bài viết được chỉnh sửa gần đây nhất."""
        return self.search([], order='last_edition_date desc, id desc', limit=limit).read(
            ['id', 'name', 'icon', 'article_type', 'last_edition_date', 'last_edition_uid']
        )

    @api.model
    def get_favorite_articles(self):
        """Bài viết yêu thích của user hiện tại."""
        return self.search([('favorite_user_ids', 'in', self.env.user.id)]).read(
            ['id', 'name', 'icon', 'article_type']
        )
        
    def action_toggle_template(self):
        self.ensure_one()
        self.is_template = not self.is_template
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Đã cập nhật'),
                'message': _('Bài viết đã được %s làm mẫu.') % (
                    _('đánh dấu') if self.is_template else _('bỏ')
                ),
                'type': 'success',
                'sticky': False,
            }
        }
    def action_create_from_template(self):
        self.ensure_one()
        new_article = self.copy({
            'name': _('(Từ mẫu) %s') % self.name,
            'is_template': False,           # bài mới không phải mẫu
            'parent_id': self.parent_id.id,
            'article_type': self.article_type,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'knowledge.article',
            'res_id': new_article.id,
            'view_mode': 'form',
            'target': 'current',
        }
    @api.model
    def get_templates(self, article_type=None):
        """Trả về danh sách mẫu — dùng cho module khác gọi vào."""
        domain = [('is_template', '=', True), ('active', '=', True)]
        if article_type:
            domain.append(('article_type', '=', article_type))
        return self.search(domain).read(['id', 'name', 'icon', 'template_description', 'article_type'])
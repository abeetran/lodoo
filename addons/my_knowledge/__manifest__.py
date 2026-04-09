# -*- coding: utf-8 -*-
{
    'name': 'Custom Knowledge (Enterprise Style)',
    'version': '17.0.2.0.0',
    'summary': 'Knowledge Base giống Enterprise - Cây bài viết, Editor phong cách Notion',
    'description': """
        Module Knowledge nâng cao theo phong cách Odoo Enterprise:
        - Giao diện 2 cột: Sidebar cây bài viết + Editor
        - Trình soạn thảo HTML phong cách Notion
        - Cấu trúc cây phân cấp (kéo thả)
        - Không gian làm việc: Workspace / Shared / Private
        - Tính năng yêu thích
        - Chia sẻ bài viết với thành viên
        - Lịch sử chỉnh sửa (Chatter)
        - Lên lịch nhắc việc (Activity)
        - Tìm kiếm toàn văn
        - Khóa/mở bài viết
        - Lưu trữ (Archive)
        - Breadcrumb điều hướng
        - Trang chủ (Home) với bài viết gần đây / yêu thích
    """,
    'author': 'Custom Dev',
    'category': 'Productivity/Knowledge',
    'depends': ['base', 'mail', 'web', 'knowledge'],
    'data': [
        'security/knowledge_security.xml',
        'security/ir.model.access.csv',
        'data/knowledge_data.xml',
        'views/knowledge_article_views.xml',
        'views/knowledge_article_member_views.xml',
        'views/knowledge_home_views.xml',
        'views/knowledge_menus.xml',
        'wizard/knowledge_invite_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'knowledge/static/src/css/knowledge.css',
            'knowledge/static/src/js/knowledge_tree.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
    'sequence': 150,
}

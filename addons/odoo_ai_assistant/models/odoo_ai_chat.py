# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.tools import html2plaintext
import logging
import requests
import json
import re
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class OdooAIKnowledge(models.Model):
    _name = 'odoo.ai.knowledge'
    _description = 'Thư viện kiến thức cho AI'
    name = fields.Char(string='Tên chủ đề', required=True)
    keyword = fields.Char(string='Từ khóa kích hoạt')
    content = fields.Text(string='Nội dung hướng dẫn', required=True)
    active = fields.Boolean(default=True)


class OdooAIUserBehavior(models.Model):
    _name = 'odoo.ai.user.behavior'
    _description = 'Theo dõi hành vi người dùng'
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    behavior_type = fields.Selection(
        [('module_visit', 'Vào Module'), ('frequent_question', 'Hỏi AI')])
    res_model = fields.Char(string='ID')
    module_name = fields.Char(string='Tên')
    count = fields.Integer(default=1)


class OdooAIChat(models.Model):
    _name = 'odoo.ai.chat'
    _description = 'Odoo AI Chat History'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Chủ đề', required=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Người gửi',
                              default=lambda self: self.env.user, readonly=True)
    history_json = fields.Text(
        string='Lịch sử luồng Chat (JSON)', default="[]")
    question = fields.Text(string='Câu hỏi cuối')
    answer = fields.Text(string='AI Trả lời cuối', readonly=True)
    suggested_action_xml_id = fields.Char(
        string='Suggested Action', readonly=True)

    @api.model
    def get_action_data(self, action_ref, domain_str=None, view_type=None):
        try:
            action = False
            if ',' in action_ref:
                model, res_id = action_ref.split(',')
                if model == 'ir.actions.act_window':
                    action = self.env[model].sudo().browse(int(res_id))
                else:
                    return {
                        'type': 'ir.actions.act_window',
                        'name': 'Chi tiết tài liệu',
                        'res_model': model,
                        'res_id': int(res_id),
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                        'target': 'new',  
                    }

            elif not str(action_ref).isdigit():
                action = self.env.ref(action_ref, raise_if_not_found=False)
            else:
                action = self.env['ir.actions.act_window'].sudo().browse(
                    int(action_ref))

            if not action or not action.exists() or action._name != 'ir.actions.act_window':
                return False

            action_dict = action.sudo().read()[0]
            action_dict.pop('help', None)

            if domain_str:
                try:
                    action_dict['domain'] = json.loads(domain_str)
                except:
                    pass

            if view_type == 'form':
                action_dict['views'] = [(False, 'form')]
                action_dict['view_mode'] = 'form'
                action_dict['res_id'] = False
                action_dict['view_id'] = False
                action_dict['search_view_id'] = False
                action_dict['target'] = 'current'

            return action_dict
        except Exception as e:
            _logger.error(f"Lỗi khi lấy Action Data: {e}")
            return False

    @api.model
    def log_user_behavior(self, behavior_type, res_model, module_name=None):
        if 'ai_chat' in str(res_model).lower() or 'odoo_ai' in str(res_model).lower():
            return
        if behavior_type == 'module_visit':
            action_valid = False
            try:
                if str(res_model).isdigit():
                    action = self.env['ir.actions.act_window'].sudo().browse(
                        int(res_model))
                    if action.exists():
                        module_name, action_valid = action.name, True
                else:
                    action = self.env.ref(res_model, raise_if_not_found=False)
                    if action:
                        module_name, action_valid = action.name, True
                if not action_valid:
                    return
            except Exception:
                return

        domain = [('user_id', '=', self.env.uid), ('behavior_type',
                                                   '=', behavior_type), ('res_model', '=', res_model)]
        existing = self.env['odoo.ai.user.behavior'].search(domain, limit=1)
        if existing:
            existing.write({'count': existing.count + 1})
        else:
            self.env['odoo.ai.user.behavior'].create(
                {'behavior_type': behavior_type, 'res_model': res_model, 'module_name': module_name or "Màn hình hệ thống"})

    @api.model
    def get_personalized_suggestions(self):
        date_limit = datetime.now() - timedelta(days=7)
        top_modules_raw = self.env['odoo.ai.user.behavior'].search_read(
            [('user_id', '=', self.env.uid), ('behavior_type', '=', 'module_visit'),
             ('create_date', '>=', date_limit), ('count', '>=', 3), ('res_model', 'not ilike', 'odoo_ai')],
            ['res_model', 'module_name', 'count'], order='count desc', limit=15
        )
        top_modules, related_modules, added_related = [], [], set()
        RELATED_MAP = {
            'bán hàng': {'name': 'Invoicing (Hóa đơn)', 'action': 'account.action_move_out_invoice_type'},
            'sale': {'name': 'Invoicing (Hóa đơn)', 'action': 'account.action_move_out_invoice_type'},
            'hóa đơn': {'name': 'Sales (Bán hàng)', 'action': 'sale.action_quotations_with_onboarding'},
            'invoicing': {'name': 'Sales (Bán hàng)', 'action': 'sale.action_quotations_with_onboarding'},
        }
        for m in top_modules_raw:
            try:
                if str(m['res_model']).isdigit() and self.env['ir.actions.act_window'].sudo().browse(int(m['res_model'])).exists():
                    top_modules.append(m)
                elif self.env.ref(m['res_model'], raise_if_not_found=False):
                    top_modules.append(m)
                mod_name_lower = (m.get('module_name') or '').lower()
                for key, rel_info in RELATED_MAP.items():
                    if key in mod_name_lower and rel_info['action'] not in added_related:
                        related_modules.append(rel_info)
                        added_related.add(rel_info['action'])
            except:
                pass
            if len(top_modules) == 3:
                break

        top_queries = self.env['odoo.ai.user.behavior'].search_read(
            [('user_id', '=', self.env.uid), ('behavior_type', '=', 'frequent_question'),
             ('create_date', '>=', date_limit), ('count', '>=', 2)],
            ['res_model', 'count'], order='count desc', limit=3
        )
        return {'modules': top_modules, 'queries': [q['res_model'] for q in top_queries], 'related': related_modules}

    def action_send(self):
        for rec in self:
            if not rec.question:
                continue
            rec.action_send_with_files(rec.question, [])

    @api.model
    def get_chat_history(self, chat_id):
        record = self.browse(int(chat_id))
        if record.exists():
            if record.history_json and record.history_json != '[]':
                try:
                    return json.loads(record.history_json)
                except:
                    pass
            msgs = []
            if record.question:
                msgs.append({'role': 'user', 'content': record.question})
            if record.answer:
                ai_msg = {'role': 'ai', 'content': record.answer}
                if record.suggested_action_xml_id:
                    ai_msg['suggested_action'] = record.suggested_action_xml_id
                msgs.append(ai_msg)
            return msgs
        return []

    @api.model
    def send_message_from_ui(self, question=None, attachments=None, chat_id=None):
        if chat_id:
            record = self.browse(int(chat_id))
            if not record.exists():
                record = self.create(
                    {'name': f'{question[:30]}...' if question else 'File Upload'})
        else:
            record = self.create(
                {'name': f'{question[:30]}...' if question else 'File Upload'})
        return record.action_send_with_files(question, attachments)

    def action_send_with_files(self, question, attachments=None):
        self.ensure_one()
        mcp_url = self.env['ir.config_parameter'].sudo().get_param(
            'mcp.server.url', 'http://mcp-server:3333/chat')
        lower_q = (question or "").lower()

        dynamic_actions = ""
        intent_create = any(kw in lower_q for kw in [
                            'tạo', 'thêm', 'mới', 'create', 'new', 'add'])

        CORE_APPS = {
            'sale': 'sale.action_quotations_with_onboarding',
            'bán hàng': 'sale.action_quotations_with_onboarding',
            'đơn hàng': 'sale.action_quotations_with_onboarding',
            'invoicing': 'account.action_move_out_invoice_type',
            'hóa đơn': 'account.action_move_out_invoice_type',
            'kế toán': 'account.action_move_out_invoice_type',
            'inventory': 'stock.action_picking_tree_all',
            'kho': 'stock.action_picking_tree_all',
            'purchase': 'purchase.purchase_rfq',
            'mua hàng': 'purchase.purchase_rfq',
            'crm': 'crm.crm_lead_action_pipeline',
            'khách hàng': 'crm.crm_lead_action_pipeline',
            'nhân sự': 'hr.open_view_employee_list_my',
            'nhân viên': 'hr.open_view_employee_list_my',
            'employee': 'hr.open_view_employee_list_my',
            'nhân công': 'hr.open_view_employee_list_my',
            'app': 'base.open_module_tree',
            'ứng dụng': 'base.open_module_tree',
            'discuss': 'mail.action_discuss',
            'thảo luận': 'mail.action_discuss'
        }

        core_matched = False
        for key, xml_id in CORE_APPS.items():
            if key in lower_q.split() or f" {key} " in f" {lower_q} ":
                action = self.env.ref(xml_id, raise_if_not_found=False)
                if not action and key in ['sale', 'bán hàng', 'đơn hàng']:
                    action = self.env.ref(
                        'sale.action_orders', raise_if_not_found=False)
                if not action and key in ['sale', 'bán hàng', 'đơn hàng']:
                    action = self.env.ref(
                        'sale.action_quotations', raise_if_not_found=False)

                if action:
                    ext_ids = action.get_external_id()
                    valid_xml_id = ext_ids.get(
                        action.id) if ext_ids else f"{action._name},{action.id}"
                    act_str = f"||OD_ACTION:{valid_xml_id}|NEW||" if intent_create else f"||OD_ACTION:{valid_xml_id}||"
                    dynamic_actions += f"- Trang Quản lý chính '{key.capitalize()}': Mã {act_str}\n"
                    core_matched = True

        if not core_matched:
            stop_words = ['vào', 'trang', 'mở', 'module', 'app', 'ứng', 'dụng', 'đi', 'đến',
                          'cho', 'tôi', 'xem', 'làm', 'sao', 'muốn', 'tạo', 'thêm', 'mới', 'của', 'các', 'một']
            clean_kws = [kw for kw in lower_q.replace('?', '').replace(
                '.', '').split() if kw not in stop_words and len(kw) >= 2]

            if clean_kws:
                search_term = " ".join(clean_kws)
                menus = self.env['ir.ui.menu'].sudo().search([
                    ('action', '!=', False),
                    '|', ('name', 'ilike', search_term), ('complete_name',
                                                          'ilike', search_term)
                ])
                menus = [m for m in menus if 'settings' not in str(
                    m.action).lower() and 'config' not in str(m.action).lower()]
                menus = sorted(menus, key=lambda m: str(
                    m.complete_name).count('/'))[:3]

                if not menus:
                    longest_kw = max(clean_kws, key=len)
                    menus = self.env['ir.ui.menu'].sudo().search([
                        ('action', '!=', False),
                        '|', ('name', 'ilike',
                              longest_kw), ('complete_name', 'ilike', longest_kw)
                    ])
                    menus = [m for m in menus if 'settings' not in str(
                        m.action).lower() and 'config' not in str(m.action).lower()]
                    menus = sorted(menus, key=lambda m: str(
                        m.complete_name).count('/'))[:3]

                if menus:
                    dynamic_actions += "\n[MÀN HÌNH TÌM THẤY TRONG HỆ THỐNG]:\n"
                    for m in menus:
                        if m.action:
                            ext_ids = m.action.get_external_id()
                            action_ref = ext_ids.get(
                                m.action.id) if ext_ids else f"{m.action._name},{m.action.id}"
                            action_str = f"||OD_ACTION:{action_ref}"
                            if intent_create:
                                action_str += "|NEW"
                            action_str += "||"
                            dynamic_actions += f"- '{m.complete_name}': {action_str}\n"

        knowledge_context = ""
        try:
            articles = self.env['knowledge.article'].sudo().search(
                [('active', '=', True)])
            query_terms = set(re.findall(r"\w+", lower_q))
            short_terms = {'pdf', 'ppt', 'pptx', 'doc', 'docx', 'xls', 'xlsx', 'word', 'excel', 'powerpoint'}
            query_terms |= (short_terms & query_terms)
            for art in articles:
                doc_name_lower = (art.name or "").lower()
                body_text = html2plaintext(art.body or '')
                body_lower = (body_text or "").lower()
                title_terms = set(w for w in re.findall(r"\w+", doc_name_lower) if len(w) > 3 or w in short_terms)
                body_terms = set(w for w in re.findall(r"\w+", body_lower) if len(w) > 3 or w in short_terms)
                if (
                    doc_name_lower in lower_q or
                    body_lower in lower_q or
                    title_terms & query_terms or
                    body_terms & query_terms
                ):
                    action_ref = f"||OD_ACTION:{art._name},{art.id}||"
                    knowledge_context += f"\n[TÀI LIỆU CÔNG TY - Tên: {art.name}]:\n{body_text}\n"
                    knowledge_context += f"(YÊU CẦU AI: Trả lời tóm tắt nội dung tài liệu trên. KHÔNG tạo link tải file ảo. BẮT BUỘC đính kèm chính xác chuỗi {action_ref} ở cuối cùng để người dùng bấm vào xem bản đầy đủ và hình ảnh).\n"
            if not knowledge_context:
                fallback_articles = self.env['knowledge.article'].sudo().search([
                    ('active', '=', True),
                    '|',
                    ('name', 'ilike', lower_q),
                    ('body', 'ilike', lower_q)
                ], limit=5)
                for art in fallback_articles:
                    body_text = html2plaintext(art.body or '')
                    action_ref = f"||OD_ACTION:{art._name},{art.id}||"
                    knowledge_context += f"\n[TÀI LIỆU CÔNG TY - Fallback - Tên: {art.name}]:\n{body_text}\n"
                    knowledge_context += f"(YÊU CẦU AI: Trả lời tóm tắt nội dung tài liệu trên. KHÔNG tạo link tải file ảo. BẮT BUỘC đính kèm chính xác chuỗi {action_ref} ở cuối cùng để người dùng bấm vào xem bản đầy đủ và hình ảnh).\n"
        except Exception as e:
            _logger.warning(
                f"Lỗi tìm kiếm Knowledge mới, chuyển sang dùng odoo.ai.knowledge: {e}")
            knowledges = self.env['odoo.ai.knowledge'].sudo().search(
                [('active', '=', True)])
            for k in knowledges:
                if k.keyword:
                    keywords = [kw.strip().lower()
                                for kw in k.keyword.split(',') if kw.strip()]
                    if any(kw in lower_q for kw in keywords):
                        knowledge_context += f"\n[HƯỚNG DẪN ĐẶC THÙ CỦA DOANH NGHIỆP - BẮT BUỘC TUÂN THỦ]: {k.content}\n"
        try:
            leads = self.env['crm.lead'].sudo().search(
                [('description', '!=', False)], limit=50, order='id desc')
            for lead in leads:
                lead_name_lower = (lead.name or "").lower()
                if lead_name_lower in lower_q or any(word in lower_q for word in lead_name_lower.split() if len(word) > 3):
                    clean_crm_note = html2plaintext(lead.description or '')
                    action_ref = f"||OD_ACTION:{lead._name},{lead.id}||"
                    knowledge_context += f"\n[GHI CHÚ CRM - Cơ hội/Khách: {lead.name}]:\n{clean_crm_note}\n"
                    knowledge_context += f"(YÊU CẦU AI BẮT BUỘC: Nếu dùng thông tin CRM này để trả lời, phải đính kèm mã {action_ref} ở cuối để người dùng bấm vào xem chi tiết gốc).\n"
        except Exception as e:
            _logger.warning(f"Lỗi khi tìm kiếm trong CRM: {e}")
        limit_match = re.search(r'(\d+)\s*(sản phẩm|mặt hàng|món)', lower_q)
        if not limit_match:
            limit_match = re.search(r'(top|thống kê)\s*(\d+)', lower_q)

        try:
            if limit_match or ("bán chạy" in lower_q and "sản phẩm" in lower_q):
                top_n = 5
                if limit_match:
                    top_n = int(limit_match.group(1) if limit_match.group(
                        1).isdigit() else limit_match.group(2))
                    if top_n <= 0:
                        top_n = 5

                reports = self.env['account.move.line'].sudo().read_group(
                    [
                        ('move_id.move_type', '=', 'out_invoice'),
                        ('move_id.state', '=', 'posted'),
                        ('product_id', '!=', False),
                        ('display_type', 'in', [False, 'product'])
                    ],
                    ['product_id', 'quantity', 'price_subtotal'],
                    ['product_id'],
                    orderby='quantity DESC', limit=top_n
                )

                if reports:
                    prod_ids = [r['product_id'][0]
                                for r in reports if r.get('product_id')]
                    product_lines = []
                    total_revenue = 0
                    for idx, r in enumerate(reports, start=1):
                        if not r.get('product_id'):
                            continue
                        qty = r.get('quantity', 0)
                        subtotal = r.get('price_subtotal', 0)
                        product_lines.append(
                            f"{idx}. {r['product_id'][1]} - Đã xuất hóa đơn {qty} cái, doanh thu {subtotal:,.0f} VNĐ")
                        total_revenue += subtotal

                    prod_str = "\n".join(product_lines)
                    domain_json = json.dumps(
                        [['product_id', 'in', prod_ids]], ensure_ascii=False)

                    answer = (
                        f"Doanh thu thực tế (đã xuất hóa đơn) của {len(prod_ids)} sản phẩm bán chạy nhất:\n{prod_str}\n"
                        f"Tổng doanh thu của {len(prod_ids)} sản phẩm này là {total_revenue:,.0f} VNĐ.\n\n"
                        "Nhấn **Xem chi tiết** để mở báo cáo thống kê Hóa đơn lọc riêng rẽ cho các sản phẩm này."
                    )

                    action_id = f"account.action_account_invoice_report_all|DOMAIN:{domain_json}"

                    history = []
                    if self.history_json and self.history_json != '[]':
                        try:
                            history = json.loads(self.history_json)
                        except:
                            history = []
                    history.append({'role': 'user', 'content': question})
                    history.append(
                        {'role': 'ai', 'content': answer, 'suggested_action': action_id})

                    self.write({
                        'question': question, 'answer': answer, 'suggested_action_xml_id': action_id,
                        'history_json': json.dumps(history, ensure_ascii=False)
                    })
                    return {'answer': answer, 'suggested_action': action_id, 'chat_id': self.id}

            elif "doanh thu" in lower_q or "tổng tiền" in lower_q:
                invoices = self.env['account.move'].sudo().search([
                    ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                    ('payment_state', 'in', ['paid', 'in_payment'])
                ])
                total_revenue = sum(invoices.mapped('amount_total_signed'))
                invoice_count = len(invoices)
                knowledge_context += f"\n[SỐ LIỆU THẬT]: Doanh thu thực tế (đã thanh toán) là: {total_revenue:,.0f} VNĐ (từ {invoice_count} hóa đơn).\n"
                knowledge_context += f"(YÊU CẦU AI: Chỉ đọc số liệu, kết thúc bằng mã: ||OD_ACTION:account.action_account_invoice_report_all||).\n"
        except Exception as e:
            _logger.error(f"Lỗi truy vấn AI: {e}")

        erp_context = ""
        try:
            installed = self.env['ir.module.module'].sudo().search(
                [('state', '=', 'installed'), ('application', '=', True)])
            inst_names = [m.shortdesc for m in installed if m.shortdesc]
            if inst_names:
                erp_context += f"\n[TRẠNG THÁI HỆ THỐNG ERP]: Odoo của người dùng HIỆN ĐANG ACTIVE (đã cài đặt) các ứng dụng: {', '.join(inst_names)}.\n"

            if any(kw in lower_q for kw in ['cài', 'hoàn thiện', 'erp', 'khuyên', 'tư vấn', 'nên', 'thiếu']):
                uninstalled = self.env['ir.module.module'].sudo().search(
                    [('state', '!=', 'installed'), ('application', '=', True)], limit=15)
                uninst_names = [
                    m.shortdesc for m in uninstalled if m.shortdesc]
                erp_context += f"[GỢI Ý]: Các ứng dụng CHƯA ACTIVE có thể cài thêm để hoàn thiện ERP: {', '.join(uninst_names)}.\n"
                erp_context += "(YÊU CẦU AI: Tư vấn dựa trên danh sách CÓ SẴN và CHƯA ACTIVE ở trên).\n"
        except Exception as e:
            pass

        system_note = _("""[System Note: Bạn là Siêu trợ lý AI của doanh nghiệp (chạy trên nền Odoo).
QUY TẮC TỐI THƯỢNG:
1. TUÂN THỦ HƯỚNG DẪN CÔNG TY: Nếu prompt có [TÀI LIỆU CÔNG TY], bạn BẮT BUỘC phải dùng nó để trả lời.
2. TUYỆT ĐỐI KHÔNG TỰ BỊA ĐƯỜNG LINK (URL): Cấm tuyệt đối việc tạo ra các đường link markdown như [Tên](https://...).
3. LUÔN đính kèm mã action ||OD_ACTION:xxx|| ở cuối câu trả lời nếu được yêu cầu, để hệ thống tự tạo nút bấm cho người dùng.
4. Cấm dùng thẻ Markdown tạo link html.] \n\n""")

        history = []
        if self.history_json and self.history_json != '[]':
            try:
                history = json.loads(self.history_json)
            except:
                pass

        full_prompt_for_ai = system_note + \
            dynamic_actions + knowledge_context + erp_context

        if history:
            full_prompt_for_ai += "--- LỊCH SỬ ---\n"
            for h_msg in history:
                full_prompt_for_ai += f"{'Người dùng' if h_msg.get('role') == 'user' else 'AI'}: {h_msg.get('content')}\n\n"

        full_prompt_for_ai += f"Người dùng (Câu hỏi mới): {question or ''}"

        payload = {"message": full_prompt_for_ai, "files": attachments or []}
        headers = {"Content-Type": "application/json"}

        try:
            res = requests.post(mcp_url, json=payload,
                                headers=headers, timeout=60).json()
            ans = res.get('reply', '')
            action_id = False
            match = re.search(r'\|\|OD_ACTION:(.*?)\|\|', ans)
            if match:
                action_id = match.group(1)
                ans = re.sub(r'\|\|OD_ACTION:.*?\|\|', '', ans).strip()

            user_msg = {"role": "user", "content": question}
            if attachments:
                user_msg["content"] += f"\n[Đã đính kèm {len(attachments)} tệp]"
            history.append(user_msg)

            ai_msg = {"role": "ai", "content": ans}
            if action_id:
                ai_msg["suggested_action"] = action_id
            history.append(ai_msg)

            self.write({
                'question': question, 'answer': ans, 'suggested_action_xml_id': action_id,
                'history_json': json.dumps(history, ensure_ascii=False)
            })
            return {'answer': ans, 'suggested_action': action_id, 'chat_id': self.id}
        except Exception as e:
            return {'chat_id': self.id, 'answer': f"Lỗi Server: {str(e)}"}

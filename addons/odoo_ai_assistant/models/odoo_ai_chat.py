# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging
import requests
import json
import re 

_logger = logging.getLogger(__name__)

class OdooAIChat(models.Model):
    _name = 'odoo.ai.chat'
    _description = 'Odoo AI Chat History'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Chủ đề', required=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Người gửi', default=lambda self: self.env.user, readonly=True)
    history_json = fields.Text(string='Lịch sử luồng Chat (JSON)', default="[]")
    question = fields.Text(string='Câu hỏi cuối', required=False)
    answer = fields.Text(string='AI Trả lời cuối', readonly=True)
    suggested_action_xml_id = fields.Char(string='Suggested Action', readonly=True)

    def action_send(self):
        for rec in self:
            if not rec.question: continue
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
            if record.question: msgs.append({'role': 'user', 'content': record.question})
            if record.answer: 
                ai_msg = {'role': 'ai', 'content': record.answer}
                if record.suggested_action_xml_id: ai_msg['suggested_action'] = record.suggested_action_xml_id
                msgs.append(ai_msg)
            return msgs
        return []

    @api.model
    def send_message_from_ui(self, question=None, attachments=None, chat_id=None):
        if chat_id:
            record = self.browse(int(chat_id))
            if not record.exists():
                record = self.create({'name': f'{question[:30]}...' if question else 'File Upload'})
        else:
            record = self.create({'name': f'{question[:30]}...' if question else 'File Upload'})
        
        return record.action_send_with_files(question, attachments)
    
    def action_send_with_files(self, question, attachments=None):
        self.ensure_one()
        mcp_url = self.env['ir.config_parameter'].sudo().get_param('mcp.server.url', 'http://mcp-server:3333/chat')
        system_note = _("[System Note: Hãy trả lời tự nhiên mọi câu hỏi của người dùng. TUY NHIÊN, nếu người dùng đặc biệt yêu cầu xem 'báo cáo doanh thu' của công ty, hãy tư vấn và LUÔN đính kèm mã '||OD_ACTION:sale.action_order_report_all||' ở cuối câu trả lời].\n\n")        
        history = []
        if self.history_json and self.history_json != '[]':
            try:
                history = json.loads(self.history_json)
            except:
                history = []
        
        full_prompt_for_ai = system_note
        if history:
            full_prompt_for_ai += "--- LỊCH SỬ TRÒ CHUYỆN TRƯỚC ĐÓ ---\n"
            for h_msg in history:
                role_str = "Người dùng" if h_msg.get("role") == "user" else "AI"
                full_prompt_for_ai += f"{role_str}: {h_msg.get('content')}\n\n"
            full_prompt_for_ai += "--- KẾT THÚC LỊCH SỬ ---\n\n"
        
        full_prompt_for_ai += f"Người dùng (Câu hỏi mới): {question or ''}"
        
        payload = {
            "message": full_prompt_for_ai,
            "files": attachments or [] 
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(mcp_url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()

            result = response.json()
            raw_answer = result.get('reply', result.get('answer', _('No answer received from AI.')))
            processed_answer = raw_answer
            action_xml_id = False
            
            match = re.search(r'\|\|OD_ACTION:(.*?)\|\|', raw_answer)
            if match:
                action_xml_id = match.group(1)
                processed_answer = re.sub(r'\|\|OD_ACTION:.*?\|\|', '', raw_answer).strip()

            user_msg = {"role": "user", "content": question}
            if attachments:
                user_msg["content"] += f"\n[Đã đính kèm {len(attachments)} tệp]"
            if question or attachments:
                history.append(user_msg)
            
            ai_msg = {"role": "ai", "content": processed_answer}
            if action_xml_id:
                ai_msg["suggested_action"] = action_xml_id
            history.append(ai_msg)

            self.write({
                'question': question,
                'answer': processed_answer,
                'suggested_action_xml_id': action_xml_id,
                'history_json': json.dumps(history, ensure_ascii=False)
            })
            
            res_data = {
                'chat_id': self.id,
                'answer': processed_answer
            }
            if action_xml_id:
                res_data['suggested_action'] = action_xml_id
            return res_data

        except Exception as e:
            _logger.error("Error AI Server: %s", str(e))
            error_msg = f"Connection Error: {str(e)}"
            history.append({"role": "user", "content": question})
            history.append({"role": "ai", "content": error_msg})
            self.write({
                'answer': error_msg,
                'history_json': json.dumps(history, ensure_ascii=False)
            })
            return {'chat_id': self.id, 'answer': error_msg}
from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)

class OdooAIChat(models.Model):
    _name = "odoo.ai.chat"
    _description = "Odoo AI Chat"
    _inherit = ['mail.thread'] 

    name = fields.Char(string="Tiêu đề", required=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', 
        string='Người gửi', 
        default=lambda self: self.env.user,
        tracking=True
    )
    question = fields.Text(string="Tin nhắn của bạn", tracking=True)
    answer = fields.Text(string="AI Trả lời", readonly=True, tracking=True)

    def action_send(self):
        mcp_url = self.env['ir.config_parameter'].sudo().get_param(
            'mcp.server.url', 'http://mcp-server:3333/chat'
        )

        for rec in self:
            if not rec.question:
                continue
                
            try:
                response = requests.post(
                    mcp_url, 
                    json={"message": rec.question}, 
                    timeout=30,
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                data = response.json()
                rec.answer = data.get("reply", "No response from AI.")

                # Đẩy tin nhắn vào khung chat UI của Odoo
                rec.message_post(body=f"<b>Bạn:</b> {rec.question}<br/><b>AI:</b> {rec.answer}")

            except requests.exceptions.RequestException as e:
                _logger.error(f"Network error connecting to MCP: {str(e)}")
                rec.answer = "Connection Error: Không thể kết nối tới Server AI."
                rec.message_post(body=rec.answer)
            except Exception as e:
                _logger.exception("Unexpected error")
                rec.answer = f"Error: {str(e)}"
                rec.message_post(body=rec.answer)
                
    @api.model
    def get_history_for_ui(self):
        records = self.search([], order='id asc', limit=50)
        res = []
        for rec in records:
            if rec.question: res.append({'role': 'user', 'content': rec.question})
            if rec.answer: res.append({'role': 'ai', 'content': rec.answer})
        return res

    @api.model
    def send_message_from_ui(self, question):
        record = self.create({
            'name': f'Chat: {question[:20]}...',
            'question': question
        })
        record.action_send()
        return {'answer': record.answer}
from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)

class OdooAIChat(models.Model):
    _name = "odoo.ai.chat"
    _description = "Odoo AI Chat"

    name = fields.Char(string="Title", required=True)
    user_id = fields.Many2one(
        'res.users', 
        string='Người gửi', 
        default=lambda self: self.env.user
    )
    question = fields.Text(string="Question")
    answer = fields.Text(string="Answer", readonly=True) # Nên để readonly để tránh sửa tay đè lên AI

    def action_send(self):
        # Lấy URL cấu hình một lần duy nhất trước vòng lặp
        mcp_url = self.env['ir.config_parameter'].sudo().get_param(
            'mcp.server.url', 'http://localhost:3333/chat'
        )

        for rec in self:
            if not rec.question:
                continue
                
            try:
                # Gửi request với headers rõ ràng
                response = requests.post(
                    mcp_url, 
                    json={"message": rec.question}, 
                    timeout=30,
                    headers={'Content-Type': 'application/json'}
                )
                
                # Kiểm tra lỗi HTTP (4xx, 5xx)
                response.raise_for_status()
                
                # Parse kết quả
                data = response.json()
                rec.answer = data.get("reply", "No response from AI.")

            except requests.exceptions.RequestException as e:
                _logger.error(f"Network error connecting to MCP: {str(e)}")
                rec.answer = f"Connection Error: Không thể kết nối tới Server AI."
            except Exception as e:
                _logger.exception("Unexpected error")
                rec.answer = f"Error: {str(e)}"
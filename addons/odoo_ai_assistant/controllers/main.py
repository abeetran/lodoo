from odoo import http
from odoo.http import request
import json

class AIChatController(http.Controller):
    
    @http.route('/api/ai/chat', type='http', auth='public', methods=['POST', 'OPTIONS'], cors='*', csrf=False)
    def api_send_message(self, **kwargs):
        
        # 1. Xử lý dứt điểm Request dò đường (Preflight) của React
        if request.httprequest.method == 'OPTIONS':
            headers = [
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'POST, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept')
            ]
            return request.make_response('', headers=headers)

        # 2. Xử lý Request POST chứa tin nhắn
        try:
            data = json.loads(request.httprequest.data)
            question = data.get('question')
            
            if not question:
                return request.make_response(json.dumps({'error': 'Thiếu câu hỏi'}), headers=[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')], status=400)

            # Tạo bản ghi trong Odoo
            chat_record = request.env['odoo.ai.chat'].sudo().create({
                'name': f'API: {question[:20]}...',
                'question': question
            })

            # Gọi mcp-server xử lý
            chat_record.action_send()

            # Quan trọng: Ép Odoo đính kèm thẻ thông hành CORS vào cả response thành công
            headers = [
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*')
            ]
            return request.make_response(json.dumps({
                'status': 'success',
                'question': question,
                'answer': chat_record.answer
            }), headers=headers)

        except Exception as e:
            # Lỗi server cũng phải đính kèm thẻ CORS, nếu không React sẽ không đọc được mã lỗi
            headers = [
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*')
            ]
            return request.make_response(json.dumps({'error': str(e)}), headers=headers, status=500)
        
    @http.route('/api/ai/chat/history', type='http', auth='public', methods=['GET', 'OPTIONS'], cors='*', csrf=False)
    def api_get_history(self, **kwargs):
        
        # 1. Xử lý CORS Preflight
        if request.httprequest.method == 'OPTIONS':
            headers = [
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'GET, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept')
            ]
            return request.make_response('', headers=headers)

        # 2. Lấy dữ liệu từ database
        try:
            # Tìm 20 tin nhắn gần nhất, sắp xếp từ cũ đến mới
            records = request.env['odoo.ai.chat'].sudo().search([], order='id asc', limit=20)
            
            history = []
            for rec in records:
                # Một bản ghi trong Odoo có cả câu hỏi và câu trả lời
                if rec.question:
                    history.append({'role': 'user', 'content': rec.question})
                if rec.answer:
                    history.append({'role': 'ai', 'content': rec.answer})

            headers = [
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*')
            ]
            return request.make_response(json.dumps({
                'status': 'success',
                'data': history
            }), headers=headers)

        except Exception as e:
            headers = [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')]
            return request.make_response(json.dumps({'error': str(e)}), headers=headers, status=500)
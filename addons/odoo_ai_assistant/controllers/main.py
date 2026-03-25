from odoo import http
from odoo.http import request
import json

class AIChatController(http.Controller):
    
    @http.route('/api/ai/chat', type='http', auth='public', methods=['POST', 'OPTIONS'], cors='*', csrf=False)
    def api_send_message(self, **kwargs):
        
        if request.httprequest.method == 'OPTIONS':
            headers = [
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'POST, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept')
            ]
            return request.make_response('', headers=headers)

        try:
            data = json.loads(request.httprequest.data)
            question = data.get('question')
            
            if not question:
                return request.make_response(json.dumps({'error': 'Thiếu câu hỏi'}), headers=[('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*')], status=400)

            chat_record = request.env['odoo.ai.chat'].sudo().create({
                'name': f'API: {question[:20]}...',
                'question': question
            })

            chat_record.action_send()

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
            headers = [
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*')
            ]
            return request.make_response(json.dumps({'error': str(e)}), headers=headers, status=500)
        
    @http.route('/api/ai/chat/history', type='http', auth='public', methods=['GET', 'OPTIONS'], cors='*', csrf=False)
    def api_get_history(self, **kwargs):
        
        if request.httprequest.method == 'OPTIONS':
            headers = [
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'GET, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept')
            ]
            return request.make_response('', headers=headers)

        try:
            records = request.env['odoo.ai.chat'].sudo().search([], order='id asc', limit=20)
            
            history = []
            for rec in records:
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
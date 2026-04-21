from odoo import http
from odoo.http import request
import json
import os
import logging

_logger = logging.getLogger(__name__)

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

    @http.route("/ai_assistant/chat", type="json", auth="user")
    def chat(self, message):

        user = request.env.user

        # ======================================================
        # 1. INTENT RESOLUTION (generic)
        # ======================================================
        intent = self._resolve_intent(message)

        # intent example:
        # {
        #   "model": "sale.order",
        #   "operation": "read",
        #   "description": "sales statistics"
        # }

        # ======================================================
        # 2. PERMISSION CHECK (GENERIC ODOO ACL)
        # ======================================================
        if intent:
            allowed = self._check_model_access(user, intent["model"], intent["operation"])

            if not allowed:
                return {
                    "type": "error",
                    "title": "Không đủ quyền",
                    "message": f"Bạn không có quyền truy cập {intent['model']}"
                }

        # ======================================================
        # 3. CALL LIBRECHAT (AI reasoning layer)
        # ======================================================
        response = self._call_librechat(user, message, intent)

        return response

    def _resolve_intent(self, message):

        msg = message.lower()

        # SALES
        if "bán hàng" in msg or "doanh thu" in msg:
            return {
                "model": "sale.order",
                "operation": "read"
            }

        # ACCOUNTING
        if "hóa đơn" in msg or "invoice" in msg:
            return {
                "model": "account.move",
                "operation": "read"
            }

        # PROJECT
        if "task" in msg or "dự án" in msg:
            return {
                "model": "project.task",
                "operation": "read"
            }

        return None
    
    def _check_model_access(self, user, model_name, operation):

        env = request.env(user=user.id)

        model = env[model_name]

        try:
            # ORM ACL check (Odoo chuẩn)
            if operation == "read":
                model.check_access_rights("read")
            elif operation == "write":
                model.check_access_rights("write")
            elif operation == "create":
                model.check_access_rights("create")
            elif operation == "unlink":
                model.check_access_rights("unlink")

            return True

        except Exception:
            return False

    def _call_librechat(self, user, message, intent):

        env = request.env.sudo()

        # ======================================================
        # 1. CONFIG (SAFE + MULTI DOMAIN READY)
        # ======================================================
        mcp_endpoint = env["ir.config_parameter"].get_param(
            "xf_mcp.endpoint",
            default="https://base-odoo.zent.work/mcp"
        )

        libre_endpoint = env["ir.config_parameter"].get_param(
            "librechat.endpoint",
            default="https://prompts-librechat.zent.work/api/chat"
        )

        # ======================================================
        # 2. CONTEXT BUILD (IMPORTANT FOR AI)
        # ======================================================
        payload = {
            "message": message,
            "context": {
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "company_id": user.company_id.id,
                    "lang": user.lang,
                },

                # 🔥 MCP TOOL CONFIG
                "tools": {
                    "type": "mcp",
                    "endpoint": mcp_endpoint,
                    "auth": {
                        "type": "bearer",
                        "token": user.api_key or ""
                    }
                },

                # 🔥 INTENT (permission already checked upstream)
                "intent": intent
            }
        }

        # ======================================================
        # 3. REQUEST (SAFE + LOGGING)
        # ======================================================
        try:
            res = requests.post(
                libre_endpoint,
                json=payload,
                timeout=30,
                headers={
                    "Content-Type": "application/json"
                }
            )

            res.raise_for_status()
            return res.json()

        except Exception as e:
            _logger.exception("LibreChat call failed")
            return {
                "type": "error",
                "message": "AI service unavailable",
                "detail": str(e)
            }
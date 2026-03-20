from odoo import http
from odoo.http import request
import json

API_TOKEN = "my_secure_token_123"  # đổi lại token của bạn

def check_token(req):
    token = req.httprequest.headers.get('Authorization')
    return token == f"Bearer {API_TOKEN}"


class LeadAPI(http.Controller):

    # 🔹 GET ALL (có pagination)
    @http.route('/api/leads', type='http', auth='public', methods=['GET'], csrf=False)
    def get_leads(self, **params):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        limit = int(params.get('limit', 10))
        offset = int(params.get('offset', 0))

        leads = request.env['crm.lead'].sudo().search([], limit=limit, offset=offset)

        data = []
        for l in leads:
            data.append({
                'id': l.id,
                'name': l.name,
                'email': l.email_from,
                'phone': l.phone,
            })

        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    # 🔹 GET ONE
    @http.route('/api/leads/<int:lead_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_lead(self, lead_id):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        lead = request.env['crm.lead'].sudo().browse(lead_id)

        if not lead.exists():
            return request.make_response("Not found", status=404)

        data = {
            'id': lead.id,
            'name': lead.name,
            'email': lead.email_from,
            'phone': lead.phone,
        }

        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    # 🔹 CREATE
    @http.route('/api/leads', type='http', auth='public', methods=['POST'], csrf=False)
    def create_lead(self):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        body = json.loads(request.httprequest.data)

        lead = request.env['crm.lead'].sudo().create({
            'name': body.get('name'),
            'email_from': body.get('email'),
            'phone': body.get('phone'),
        })

        return request.make_response(json.dumps({'id': lead.id}), headers=[('Content-Type', 'application/json')])

    # 🔹 UPDATE
    @http.route('/api/leads/<int:lead_id>', type='http', auth='public', methods=['PUT'], csrf=False)
    def update_lead(self, lead_id):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        lead = request.env['crm.lead'].sudo().browse(lead_id)

        if not lead.exists():
            return request.make_response("Not found", status=404)

        body = json.loads(request.httprequest.data)

        lead.write({
            'name': body.get('name'),
            'email_from': body.get('email'),
            'phone': body.get('phone'),
        })

        return request.make_response(json.dumps({'success': True}), headers=[('Content-Type', 'application/json')])

    # 🔹 DELETE
    @http.route('/api/leads/<int:lead_id>', type='http', auth='public', methods=['DELETE'], csrf=False)
    def delete_lead(self, lead_id):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        lead = request.env['crm.lead'].sudo().browse(lead_id)

        if not lead.exists():
            return request.make_response("Not found", status=404)

        lead.unlink()

        return request.make_response(json.dumps({'success': True}), headers=[('Content-Type', 'application/json')])
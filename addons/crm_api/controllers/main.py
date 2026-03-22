import json
import os
import xmlrpc.client
from urllib.parse import urlparse
from odoo import http
from odoo.http import request

API_TOKEN = os.getenv("CRM_API_TOKEN", "default_token")

def check_token(req):
    token = req.httprequest.headers.get('Authorization')
    return token == f"Bearer {API_TOKEN}"


class LeadAPI(http.Controller):

    def _get_rpc(self):
        # 👉 ĐỔI MẶC ĐỊNH SANG HTTP
        url = os.getenv("CRM_RPC_URL", "http://odoo_tik:8069")
        db = os.getenv("CRM_RPC_DB", "odoo")
        username = os.getenv("CRM_RPC_USER", "abeetran@gmail.com")
        password = os.getenv("CRM_RPC_PASSWORD", "Abcd@1234")

        parsed = urlparse(url)
        print("RPC URL:", url)

        # 👉 FIX SSL: nếu là https thì bỏ verify (cho dev)
        if parsed.scheme == 'https':
            import ssl
            context = ssl._create_unverified_context()
            common = xmlrpc.client.ServerProxy(
                f'{url}/xmlrpc/2/common',
                context=context,
                allow_none=True
            )
            models = xmlrpc.client.ServerProxy(
                f'{url}/xmlrpc/2/object',
                context=context,
                allow_none=True
            )
        else:
            # 👉 HTTP (localhost)
            common = xmlrpc.client.ServerProxy(
                f'{url}/xmlrpc/2/common',
                allow_none=True
            )
            models = xmlrpc.client.ServerProxy(
                f'{url}/xmlrpc/2/object',
                allow_none=True
            )

        uid = common.authenticate(db, username, password, {})

        if not uid:
            raise Exception("RPC Authentication failed")

        return db, uid, password, models


    def _format_lead(self, lead):
        return {
            'id': lead.get('id'),
            'name': lead.get('name') or '',
            'email': lead.get('email_from') or '',
            'phone': lead.get('phone') or '',
            'expected_revenue': float(lead.get('expected_revenue') or 0),
            'priority': int(lead.get('priority') or 0),
            'stage': {
                'id': lead['stage_id'][0] if lead.get('stage_id') else None,
                'name': lead['stage_id'][1] if lead.get('stage_id') else ''
            }
        }


    @http.route('/api/leads', type='http', auth='public', methods=['GET'], csrf=False)
    def get_leads(self, **params):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        try:
            db, uid, password, models = self._get_rpc()

            limit = int(params.get('limit', 10))
            offset = int(params.get('offset', 0))

            leads = models.execute_kw(
                db, uid, password,
                'crm.lead', 'search_read',
                [[]],
                {
                    'fields': [
                        'name', 'email_from', 'phone',
                        'expected_revenue', 'priority', 'stage_id'
                    ],
                    'limit': limit,
                    'offset': offset
                }
            )

            data = [self._format_lead(l) for l in leads]

            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            return request.make_response(str(e), status=500)


    @http.route('/api/leads/<int:lead_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_lead(self, lead_id):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        try:
            db, uid, password, models = self._get_rpc()

            leads = models.execute_kw(
                db, uid, password,
                'crm.lead', 'search_read',
                [[['id', '=', lead_id]]],
                {
                    'fields': [
                        'name', 'email_from', 'phone',
                        'expected_revenue', 'priority', 'stage_id'
                    ],
                    'limit': 1
                }
            )

            if not leads:
                return request.make_response("Not found", status=404)

            data = self._format_lead(leads[0])

            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            return request.make_response(str(e), status=500)


    @http.route('/api/leads', type='http', auth='public', methods=['POST'], csrf=False)
    def create_lead(self):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        try:
            db, uid, password, models = self._get_rpc()
            body = json.loads(request.httprequest.data)

            lead_id = models.execute_kw(
                db, uid, password,
                'crm.lead', 'create',
                [{
                    'name': body.get('name'),
                    'email_from': body.get('email'),
                    'phone': body.get('phone'),
                    'expected_revenue': float(body.get('expected_revenue') or 0),
                    'priority': body.get('priority'),
                }]
            )

            return request.make_response(
                json.dumps({'id': lead_id}),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            return request.make_response(str(e), status=500)


    @http.route('/api/leads/<int:lead_id>', type='http', auth='public', methods=['PUT'], csrf=False)
    def update_lead(self, lead_id):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        try:
            db, uid, password, models = self._get_rpc()
            body = json.loads(request.httprequest.data)

            vals = {}

            if body.get('name'):
                vals['name'] = body.get('name')

            if body.get('email'):
                vals['email_from'] = body.get('email')

            if body.get('phone'):
                vals['phone'] = body.get('phone')

            if body.get('expected_revenue') is not None:
                vals['expected_revenue'] = float(body.get('expected_revenue'))

            if body.get('priority') is not None:
                vals['priority'] = str(body.get('priority'))  # ⚠️ phải là string

            # ✅ xử lý stage
            stage = body.get('stage')
            if stage in [1, 2, 3, 4]:
                # map stage API → stage_id thực trong Odoo
                stage_map = {
                    1: 1,
                    2: 2,
                    3: 3,
                    4: 4
                }
                vals['stage_id'] = stage_map[stage]

            # 👉 chỉ write khi có dữ liệu
            if vals:
                success = models.execute_kw(
                    db, uid, password,
                    'crm.lead', 'write',
                    [[lead_id], vals]
                )
            else:
                success = False

            return request.make_response(
                json.dumps({'success': success}),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            return request.make_response(str(e), status=500)


    @http.route('/api/leads/<int:lead_id>', type='http', auth='public', methods=['DELETE'], csrf=False)
    def delete_lead(self, lead_id):
        if not check_token(request):
            return request.make_response("Unauthorized", status=401)

        try:
            db, uid, password, models = self._get_rpc()

            success = models.execute_kw(
                db, uid, password,
                'crm.lead', 'unlink',
                [[lead_id]]
            )

            return request.make_response(
                json.dumps({'success': success}),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            return request.make_response(str(e), status=500)
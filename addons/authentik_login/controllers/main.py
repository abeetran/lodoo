import os
import logging
import requests

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home

_logger = logging.getLogger(__name__)

AUTHENTIK_URL = os.environ.get(
    "AUTHENTIK_URL",
    "http://authentik-server:9000"
)

AUTHENTIK_TOKEN = os.environ.get(
    "AUTHENTIK_TOKEN",
    "")


def _ensure_db():
    """Session chỉ được ghi ra disk khi đã gắn database."""
    try:
        request.session.ensure_db()
    except Exception:
        db = getattr(request, "db", None)
        if db:
            request.session.db = db


def _save_session():
    _ensure_db()
    request.session.modified = True
    try:
        from odoo.http import root
        if getattr(request.session, "can_save", True):
            root.session_store.save(request.session)
    except Exception:
        _logger.debug("session save skipped", exc_info=True)


def _fix_stale_session_cookie():
    """Cookie trỏ sid cũ nhưng file không tồn tại → tạo sid mới và ghi file."""
    import os
    from odoo.http import root

    _ensure_db()
    store = root.session_store
    sid = request.session.sid
    if not sid:
        _save_session()
        return
    path = store.get_session_filename(sid)
    if os.path.isfile(path):
        return
    db = request.session.db or getattr(request, "db", None) or "odoo"
    _logger.info("Stale session cookie sid=%s — rotate and save new session file", sid)
    request.session.sid = store.generate_key()
    request.session.db = db
    request.session.uid = None
    request.session.login = None
    request.session.session_token = None
    request.session.modified = True
    store.save(request.session)


class AuthentikLogin(http.Controller):

    # ==========================
    # Custom Login Page
    # ==========================
    @http.route(
        "/web/login",
        auth="public",
        type="http",
        website=True
    )
    def authentik_login_page(self, **kw):
        _fix_stale_session_cookie()

        if request.session.uid:
            return request.redirect("/web")

        return request.render(
            "authentik_login.authentik_login_page",
            {
                "error": kw.get("error")
            }
        )

    # ==========================
    # Authentik API Verify
    # ==========================
    def _authenticate(self, email, password):

        try:
            url = f"{AUTHENTIK_URL}/api/login"

            headers = {
                "Authorization": f"Bearer {AUTHENTIK_TOKEN}",
                "Content-Type": "application/json"
            }

            payload = {
                "email": email,
                "password": password
            }

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                return False

            return response.json()

        except Exception:
            _logger.exception("Authentik Login Error")
            return False

    # ==========================
    # Authentik Login POST
    # ==========================
    @http.route(
        "/authentik/login",
        auth="public",
        type="http",
        methods=["POST"],
        csrf=True
    )
    def authentik_login(self, **post):
        _fix_stale_session_cookie()

        email = post.get("email")
        password = post.get("password")

        if not email or not password:
            resp = request.redirect("/web/login?error=1")
            _save_session()
            return resp

        _logger.info("Authentik login attempt email=%s", email)

        result = self._authenticate(email, password)

        if not result:
            resp = request.redirect("/web/login?error=1")
            _save_session()
            return resp

        Users = request.env["res.users"].sudo()

        user = Users.search([("login", "=", email)], limit=1)

        if not user:
            user = Users.create({
                "name": result.get("name", email),
                "login": email,
                "email": email,
                "password": password,
                "authentik_uid": result.get("id"),
                "authentik_email": email,
            })
        else:
            user.write({
                "password": password,
                "authentik_uid": result.get("id"),
                "authentik_email": email,
            })

        resp = request.redirect("/web/odoo_login?login=%s" % email)
        _save_session()
        return resp
        
    # ==========================
    # Odoo login wrapper (FIXED)
    # ==========================
    @http.route(
        "/web/odoo_login",
        auth="public",
        type="http",
        website=True
    )
    def odoo_login(self, **kw):
        _fix_stale_session_cookie()

        if request.session.uid:
            return request.redirect("/web")

        return request.render(
            "authentik_login.odoo_login",
            {
                "error": kw.get("error"),
                "login": kw.get("login", "")
            }
        )

    # ==========================
    # POST login Odoo chuẩn FIX
    # ==========================
    @http.route(
        "/web/odoo_login_post",
        auth="public",
        type="http",
        methods=["POST"],
        csrf=True
    )
    def odoo_login_post(self, **post):
        _fix_stale_session_cookie()

        login = post.get("login")
        password = post.get("password")

        try:
            uid = request.session.authenticate(
                request.db,
                login,
                password
            )

            if uid:
                return request.redirect("/web")

        except Exception:
            _logger.exception("Odoo login failed")

        return request.redirect(
            "/web/odoo_login?error=1&login=%s" % (login or "")
        )
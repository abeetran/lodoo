import os
import logging
import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

AUTHENTIK_URL = os.environ.get(
    "AUTHENTIK_URL",
    "http://authentik-server:9000"
)

AUTHENTIK_TOKEN = os.environ.get(
    "AUTHENTIK_TOKEN",
    "")


class AuthentikLogin(http.Controller):

    # /web/login: Odoo chuẩn — template web.login + inherit authentik_login_only.xml

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

        email = post.get("email")
        password = post.get("password")

        print('thong tin dangnhap', email, password)

        if not email or not password:
            return request.redirect("/web/login?error=1")

        _logger.info("Authentik login attempt email=%s", email)

        # ✅ QUAN TRỌNG: gọi API Authentik
        result = self._authenticate(email, password)

        if not result:
            return request.redirect("/web/login?error=1")

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

        return request.redirect("/web/odoo_login?login=%s" % email)
        
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

        if request.session.uid:
            return request.redirect("/web")

        return request.render(
            "myskin.odoo_login",
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
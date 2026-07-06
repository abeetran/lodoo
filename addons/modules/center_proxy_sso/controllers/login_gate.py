# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db

_logger = logging.getLogger(__name__)

_SSO_LOGIN_FALSE = frozenset({"false", "0", "no", "off"})
_SSO_ERROR_MESSAGES = {
    "missing_token": "Thiếu token SSO.",
    "invalid_token": "Token SSO không hợp lệ hoặc đã hết hạn.",
    "token_used": "Token SSO đã được sử dụng.",
    "no_email": "Token SSO thiếu email.",
    "no_user": "Không tìm thấy user Odoo cho email trong token.",
    "inactive_user": "Tài khoản Odoo đã bị vô hiệu hóa.",
    "tenant_mismatch": "Token SSO không khớp tenant.",
    "not_configured": "Odoo chưa cấu hình JWT_SECRET.",
    "server": "Lỗi máy chủ khi xử lý SSO.",
}


def _password_login_allowed(kw):
    raw = (kw.get("sso_login") or request.params.get("sso_login") or "").strip().lower()
    return raw in _SSO_LOGIN_FALSE


def _sso_error_message(code):
    key = (code or "").strip().lower()
    if not key:
        return ""
    return _SSO_ERROR_MESSAGES.get(key, f"Lỗi SSO: {key}")


def _ensure_public_env():
    """Giống web_login — login_layout cần public user (tránh res.users() singleton lỗi)."""
    if request.env.uid is None:
        if request.session.uid is None:
            request.env["ir.http"]._auth_method_public()
        else:
            request.update_env(user=request.session.uid)


class CenterLoginGate(Home):
    """Chỉ hiện form /web/login khi ?sso_login=false — SSO qua Center launch token."""

    @http.route()
    def web_login(self, redirect=None, **kw):
        ensure_db()

        if request.session.uid:
            return super().web_login(redirect=redirect, **kw)

        if _password_login_allowed(kw):
            return super().web_login(redirect=redirect, **kw)

        if request.httprequest.method == "POST":
            _logger.warning("Blocked POST /web/login without sso_login=false")
            return request.redirect("/web/login", code=303, local=True)

        _ensure_public_env()
        sso_error = kw.get("sso_error") or request.params.get("sso_error")
        values = {
            "sso_error": _sso_error_message(sso_error),
            "sso_error_code": sso_error or "",
        }
        try:
            values["databases"] = http.db_list()
        except Exception:
            values["databases"] = None

        response = request.render("center_proxy_sso.login_center_only", values)
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response

# -*- coding: utf-8 -*-
import logging
import os

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.utils import ensure_db

from odoo.addons.center_proxy_sso.lib.jwt_utils import JwtError, verify_hs256

_logger = logging.getLogger(__name__)


def _env(name):
    return (os.environ.get(name) or "").strip()


def _jwt_secret():
    return _env("JWT_SECRET") or _env("ODOO_SSO_JWT_SECRET")


def _expected_tenant_id():
    return _env("CENTER_TENANT_ID") or _env("TRIAL_TENANT_ID")


def _safe_redirect_path(raw):
    path = (raw or "/web").strip()
    if not path.startswith("/"):
        path = "/" + path
    if path.startswith("//") or "://" in path:
        return "/web"
    return path


class CenterSsoLaunch(http.Controller):
    """Nhận one-time JWT từ FastAPI center manager → tạo session Odoo."""

    @http.route("/web/sso/consume", type="http", auth="none", csrf=False, sitemap=False)
    def consume(self, token=None, redirect=None, **kw):
        ensure_db()

        if not token:
            _logger.warning("SSO consume: thiếu token")
            return request.redirect("/web/login?sso_error=missing_token", code=303)

        secret = _jwt_secret()
        if not secret:
            _logger.error("SSO consume: thiếu JWT_SECRET trên container Odoo")
            return request.redirect("/web/login?sso_error=not_configured", code=303)

        try:
            claims = verify_hs256(token, secret)
        except JwtError as exc:
            _logger.warning("SSO consume: JWT invalid — %s", exc)
            return request.redirect("/web/login?sso_error=invalid_token", code=303)

        jti = (claims.get("jti") or "").strip()
        email = (
            (claims.get("email") or claims.get("preferred_username") or "")
            .strip()
            .lower()
        )
        tenant_id = (claims.get("tenant_id") or "").strip()
        expected_tenant = _expected_tenant_id()

        if not jti:
            _logger.warning("SSO consume: thiếu jti trong JWT")
            return request.redirect("/web/login?sso_error=invalid_token", code=303)

        if not email:
            _logger.warning("SSO consume: thiếu email trong JWT")
            return request.redirect("/web/login?sso_error=no_email", code=303)

        if expected_tenant and tenant_id and tenant_id != expected_tenant:
            _logger.warning(
                "SSO consume: tenant_id JWT=%s khác CENTER_TENANT_ID=%s",
                tenant_id,
                expected_tenant,
            )
            return request.redirect("/web/login?sso_error=tenant_mismatch", code=303)

        Consumed = request.env["center.sso.consumed.jti"].sudo()
        if Consumed.search_count([("jti", "=", jti)]):
            _logger.warning("SSO consume: jti đã dùng — %s", jti)
            return request.redirect("/web/login?sso_error=token_used", code=303)

        Users = request.env["res.users"].sudo()
        user = Users.search([("login", "=ilike", email)], limit=1)
        if not user:
            user = Users.search([("email", "=ilike", email)], limit=1)
        if not user:
            _logger.warning("SSO consume: không tìm thấy user email=%s", email)
            return request.redirect("/web/login?sso_error=no_user", code=303)

        if not user.active:
            _logger.warning("SSO consume: user inactive email=%s", email)
            return request.redirect("/web/login?sso_error=inactive_user", code=303)

        try:
            Consumed.create({
                "jti": jti,
                "email": email,
                "tenant_id": tenant_id or expected_tenant or False,
            })
            request.env.cr.commit()
        except Exception:
            _logger.exception("SSO consume: ghi jti thất bại (có thể race)")
            request.env.cr.rollback()
            if Consumed.search_count([("jti", "=", jti)]):
                return request.redirect("/web/login?sso_error=token_used", code=303)
            return request.redirect("/web/login?sso_error=server", code=303)

        request.session.uid = user.id
        request.session.login = user.login
        request.session.session_token = user._compute_session_token(request.session.sid)
        request.session.rotate = True

        if request.session.is_dirty:
            from odoo import http as odoo_http
            odoo_http.root.session_store.save(request.session)

        target = _safe_redirect_path(redirect)
        _logger.info(
            "SSO consume OK user=%s tenant=%s → %s",
            user.login,
            tenant_id or expected_tenant or "-",
            target,
        )
        return request.redirect(target, code=303, local=True)

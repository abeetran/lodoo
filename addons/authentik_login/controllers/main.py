# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AuthentikLogin(http.Controller):

    @http.route(
        "/web/odoo_login",
        auth="public",
        type="http",
        website=True,
        sitemap=False,
    )
    def odoo_login(self, **kw):
        if request.session.uid:
            return request.redirect("/web")

        return request.render(
            "authentik_login.odoo_login",
            {
                "error": kw.get("error"),
                "login": kw.get("login", ""),
            },
        )

    @http.route(
        "/web/odoo_login_post",
        auth="public",
        type="http",
        methods=["POST"],
        csrf=True,
        website=True,
        sitemap=False,
    )
    def odoo_login_post(self, **post):
        login = post.get("login")
        password = post.get("password")

        try:
            uid = request.session.authenticate(request.db, login, password)
            if uid:
                return request.redirect("/web")
        except Exception:
            _logger.exception("Odoo login failed")

        return request.redirect("/web/odoo_login?error=1&login=%s" % (login or ""))

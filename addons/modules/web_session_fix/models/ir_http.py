# -*- coding: utf-8 -*-
import os

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _pre_dispatch(cls, rule, args):
        cls._reset_stale_session_cookie()
        return super()._pre_dispatch(rule, args)

    @classmethod
    def _reset_stale_session_cookie(cls):
        """Cookie session_id còn nhưng file đã mất → session mới + ghi disk."""
        if request.session.uid:
            return
        path = request.httprequest.path
        if path == "/web/sso/consume":
            return
        sid = request.httprequest.cookies.get("session_id")
        if not sid:
            return

        from odoo import http as odoo_http

        try:
            path = odoo_http.root.session_store.get_session_filename(sid)
        except ValueError:
            return
        if os.path.isfile(path):
            return

        request.session = odoo_http.root.session_store.new()
        dbs = odoo_http.db_list(force=True)
        if len(dbs) == 1:
            request.session.update(odoo_http.get_default_session(), db=dbs[0])
            request.session.context["lang"] = request.default_lang()
        if request.session.is_dirty:
            odoo_http.root.session_store.save(request.session)

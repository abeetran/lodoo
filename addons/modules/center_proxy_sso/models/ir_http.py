# -*- coding: utf-8 -*-
import logging
import os

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

_SSO_CONSUME_PATH = "/web/sso/consume"


def _env(name):
    return (os.environ.get(name) or "").strip()


def _proxy_prefix():
    """Prefix public URL qua center, vd. /odoo/{tenant_id}."""
    header = (request.httprequest.headers.get("X-Script-Name") or "").strip()
    if header:
        prefix = header.rstrip("/")
    else:
        prefix = _env("CENTER_PROXY_PREFIX").rstrip("/")
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    return prefix


def _is_center_proxied_request():
    return bool(_proxy_prefix())


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _pre_dispatch(cls, rule, args):
        cls._apply_center_proxy_prefix()
        return super()._pre_dispatch(rule, args)

    @classmethod
    def _apply_center_proxy_prefix(cls):
        """Werkzeug SCRIPT_NAME — link/redirect tương đối khớp /odoo/{tenant}/."""
        prefix = _proxy_prefix()
        if not prefix:
            return
        request.httprequest.environ["SCRIPT_NAME"] = prefix
        _logger.debug("Center proxy SCRIPT_NAME=%s", prefix)

    @classmethod
    def _post_dispatch(cls, response):
        response = cls._center_proxy_rewrite_location(response)
        return super()._post_dispatch(response)

    @classmethod
    def _center_proxy_rewrite_location(cls, response):
        """Redirect Location: /web → /odoo/{tenant}/web khi đi qua center proxy."""
        prefix = _proxy_prefix()
        if not prefix or response.status_code not in (301, 302, 303, 307, 308):
            return response
        location = response.headers.get("Location")
        if not location or not location.startswith("/"):
            return response
        if location.startswith(prefix + "/") or location == prefix:
            return response
        response.headers["Location"] = prefix + location
        return response

    @classmethod
    def _get_public_base_url(cls):
        """URL gốc khi request đi qua center proxy (iframe same-origin)."""
        if _is_center_proxied_request():
            center_base = _env("CENTER_PUBLIC_BASE_URL").rstrip("/")
            if center_base:
                return center_base
            # Fallback: scheme + host + prefix
            proto = (
                request.httprequest.headers.get("X-Forwarded-Proto")
                or request.httprequest.scheme
            )
            host = (
                request.httprequest.headers.get("X-Forwarded-Host")
                or request.httprequest.host
            )
            return f"{proto}://{host}{_proxy_prefix()}"
        direct = _env("SERVICE_URL_ODOO").rstrip("/")
        if direct:
            return direct
        return request.httprequest.url_root.rstrip("/")

# -*- coding: utf-8 -*-
import json
import logging
import os

import requests
import werkzeug.urls

from odoo import http
from odoo.http import request
from odoo.addons.auth_oauth.controllers.main import (
    OAuthController,
    OAuthLogin,
)
from odoo.addons.web.controllers.utils import ensure_db

_logger = logging.getLogger(__name__)


def _auto_login_enabled():
    return os.environ.get("OAUTH_AUTO_LOGIN", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _authentik_base_url():
    return (os.environ.get("AUTHENTIK_PUBLIC_URL") or "").strip().rstrip("/")


def _authentik_slug():
    return (os.environ.get("AUTHENTIK_SLUG") or "").strip().strip("/")


def _authentik_token_endpoint():
    base = _authentik_base_url()
    slug = _authentik_slug()
    if not base:
        return ""
    if slug:
        return f"{base}/application/o/{slug}/token/"
    return f"{base}/application/o/token/"


def _absolute_endpoint(endpoint):
    """Chuẩn hóa auth_endpoint — tránh redirect về localhost khi chỉ lưu path."""
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return endpoint
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    base = _authentik_base_url()
    if not base:
        return endpoint
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return base + endpoint


def _oauth_redirect_uri():
    """Dùng SERVICE_URL_ODOO (khớp Authentik) thay vì url_root (proxy_mode có thể sai)."""
    base = (os.environ.get("SERVICE_URL_ODOO") or "").strip().rstrip("/")
    if base:
        return base + "/auth_oauth/signin"
    return request.httprequest.url_root.rstrip("/") + "/auth_oauth/signin"


def _exchange_authorization_code(code, redirect_uri):
    """Đổi authorization code → access_token (Authentik không hỗ trợ implicit flow)."""
    token_url = _authentik_token_endpoint()
    client_id = (os.environ.get("AUTHENTIK_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("AUTHENTIK_CLIENT_SECRET") or "").strip()
    if not token_url or not client_id:
        raise ValueError("Thiếu AUTHENTIK_PUBLIC_URL hoặc AUTHENTIK_CLIENT_ID")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret

    response = requests.post(token_url, data=data, timeout=15)
    if not response.ok:
        _logger.error(
            "OAuth token exchange failed (%s): %s",
            response.status_code,
            response.text[:500],
        )
        response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise ValueError("Token response không có access_token")
    return access_token


class OAuthAutoLogin(OAuthLogin):
    """Tự redirect /web/login → Authentik (auth_oauth). Bỏ qua khi ?no_sso=1."""

    def _authentik_provider(self):
        Provider = request.env["auth.oauth.provider"].sudo()
        client_id = (os.environ.get("AUTHENTIK_CLIENT_ID") or "").strip()
        name = (os.environ.get("OAUTH_PROVIDER_NAME") or "Authentik").strip()

        if client_id:
            provider = Provider.search(
                [("enabled", "=", True), ("client_id", "=", client_id)],
                limit=1,
            )
            if provider:
                return provider

        return Provider.search(
            [("enabled", "=", True), ("name", "=", name)],
            limit=1,
        )

    def _build_auth_link(self, provider):
        provider_data = provider.read()[0]
        auth_endpoint = _absolute_endpoint(provider_data.get("auth_endpoint"))
        if not auth_endpoint:
            return None

        state = self.get_state(provider_data)
        params = dict(
            response_type="code",
            client_id=provider_data.get("client_id"),
            redirect_uri=_oauth_redirect_uri(),
            scope=provider_data.get("scope"),
            state=json.dumps(state),
        )
        self._last_auth_endpoint = auth_endpoint
        return "%s?%s" % (auth_endpoint, werkzeug.urls.url_encode(params))

    def list_providers(self):
        """Nút OAuth trên form login cũng dùng authorization code (Authentik)."""
        providers = super().list_providers()
        client_id = (os.environ.get("AUTHENTIK_CLIENT_ID") or "").strip()
        for provider in providers:
            if client_id and provider.get("client_id") != client_id:
                continue
            auth_endpoint = _absolute_endpoint(provider.get("auth_endpoint"))
            if not auth_endpoint:
                continue
            params = dict(
                response_type="code",
                client_id=provider.get("client_id"),
                redirect_uri=_oauth_redirect_uri(),
                scope=provider.get("scope"),
                state=json.dumps(self.get_state(provider)),
            )
            provider["auth_link"] = "%s?%s" % (
                auth_endpoint,
                werkzeug.urls.url_encode(params),
            )
        return providers

    @http.route()
    def web_login(self, *args, **kw):
        ensure_db()

        if request.session.uid:
            redirect = request.params.get("redirect") or "/web"
            return request.redirect(redirect, local=True)

        if request.params.get("no_sso"):
            return super().web_login(*args, **kw)

        if request.httprequest.method != "GET":
            return super().web_login(*args, **kw)

        if request.params.get("oauth_error") or request.params.get("error"):
            return super().web_login(*args, **kw)

        if not _auto_login_enabled():
            return super().web_login(*args, **kw)

        try:
            provider = self._authentik_provider()
            auth_link = self._build_auth_link(provider) if provider else None
            auth_endpoint = getattr(self, "_last_auth_endpoint", "")
        except Exception:
            _logger.exception("OAuth auto-login failed")
            auth_link = None
            auth_endpoint = ""

        if auth_link:
            _logger.info(
                "OAuth auto-login redirect → %s (redirect_uri=%s)",
                auth_endpoint,
                _oauth_redirect_uri(),
            )
            return request.redirect(auth_link, code=303, local=False)

        return super().web_login(*args, **kw)


class OAuthAutoSignin(OAuthController):
    """Callback /auth_oauth/signin — authorization code flow (không dùng implicit/hash)."""

    @http.route("/auth_oauth/signin", type="http", auth="none")
    def signin(self, **kw):
        ensure_db()

        qs = request.httprequest.query_string.decode() if request.httprequest.query_string else ""
        _logger.info(
            "OAuth signin hit path=%s query=%s keys=%s",
            request.httprequest.path,
            qs[:200] if qs else "(empty)",
            sorted(kw.keys()),
        )

        if not kw:
            _logger.warning(
                "OAuth signin không có code/state — Authentik chưa redirect đúng "
                "(cần redirect URI: %s)",
                _oauth_redirect_uri(),
            )
            return request.redirect("/web/login?oauth_error=2", code=303, local=True)

        if kw.get("error"):
            _logger.warning(
                "OAuth provider error: %s — %s",
                kw.get("error"),
                kw.get("error_description"),
            )
            return request.redirect("/web/login?oauth_error=2", code=303, local=True)

        if kw.get("code") and not kw.get("access_token"):
            try:
                redirect_uri = _oauth_redirect_uri()
                kw["access_token"] = _exchange_authorization_code(
                    kw["code"], redirect_uri
                )
            except Exception:
                _logger.exception("OAuth authorization code exchange failed")
                return request.redirect("/web/login?oauth_error=2", code=303, local=True)

        return super().signin(**kw)

# -*- coding: utf-8 -*-
import logging
import os
import secrets
import urllib.parse

import requests
from werkzeug.utils import redirect

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _cfg(key, default=""):
    """Read config from ir.config_parameter"""
    return request.env["ir.config_parameter"].sudo().get_param(key, default=default)


def _as_bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _ensure_db():
    """Ensure db is selected for session."""
    try:
        request.session.ensure_db()
    except Exception:
        pass


def _public_url():
    """
    URL used for browser redirect to Authentik.
    In docker (host browser): http://localhost:9000
    """
    url = (os.getenv("AUTHENTIK_PUBLIC_URL") or "").strip().rstrip("/")
    if url:
        return url

    url = (_cfg("authentik.public_url") or "").strip().rstrip("/")
    if url:
        return url

    url = (_cfg("authentik.base_url") or "").strip().rstrip("/")
    if url:
        return url

    return "http://localhost:9000"


def _internal_url():
    """
    URL used for server-to-server calls (Odoo -> Authentik).
    In docker network: http://authentik-server:9000
    """
    url = (os.getenv("AUTHENTIK_INTERNAL_URL") or "").strip().rstrip("/")
    if url:
        return url

    url = (_cfg("authentik.internal_url") or "").strip().rstrip("/")
    if url:
        return url

    url = (_cfg("authentik.base_url") or "").strip().rstrip("/")
    if url:
        return url

    return "http://authentik-server:9000"


def _odoo_base_url():
    """Prefer configured web.base.url"""
    base = (_cfg("web.base.url") or "").strip().rstrip("/")
    if base:
        return base
    # fallback
    return request.httprequest.url_root.strip().rstrip("/")


def _oidc_slug():
    """
    Authentik provider/application slug.
    Example: authentik
    """
    return (_cfg("authentik.slug") or "").strip().strip("/")


def _verify_ssl():
    """
    Default skip verify in local docker.
    authentik.insecure_skip_verify_ssl=1 -> skip verify
    """
    return not _as_bool(_cfg("authentik.insecure_skip_verify_ssl", "1"))


def _clear_sso_session_keys():
    for k in [
        "authentik_state",
        "authentik_nonce",
        "authentik_token",
        "authentik_userinfo",
        "authentik_access_token",
        "authentik_id_token",
    ]:
        request.session.pop(k, None)


def _logout_local_session():
    """
    Clear Odoo session safely.
    Avoid breaking session_token (Odoo 17 security.check_session).
    """
    _ensure_db()

    # clear our own keys
    _clear_sso_session_keys()

    # rotate session id to invalidate old token
    try:
        request.session.rotate = True
    except Exception:
        pass

    # Odoo logout
    try:
        request.session.logout(keep_db=True)
    except Exception:
        _logger.exception("session.logout failed (ignored)")


def _odoo_login_user(user):
    s = request.session

    if not s.db:
        s.db = request.env.cr.dbname

    # rotate only if callable
    rot = getattr(s, "rotate", None)
    if callable(rot):
        try:
            rot()
        except Exception:
            _logger.exception("session.rotate() failed")

    # set session user
    s.uid = user.id
    s.login = user.login

    # Odoo 17: don't set request.uid directly
    request.update_env(user=user)

    # must have session_token
    if not getattr(s, "session_token", None):
        s.session_token = secrets.token_urlsafe(32)

    # force persist
    s.modified = True

    _logger.info("[LOGIN OK] db=%s uid=%s sid=%s token=%s",
                 s.db, s.uid, getattr(s, "sid", None),
                 "SET" if s.session_token else "EMPTY")
    return True


def _discover_endpoints(base_internal, slug, verify_ssl=True):
    """
    Discover endpoints from authentik provider slug and rewrite endpoints
    from PUBLIC host (localhost) to INTERNAL docker host.
    """
    well_known = f"{base_internal}/application/o/{slug}/.well-known/openid-configuration"
    resp = requests.get(
        well_known,
        headers={"Accept": "application/json"},
        timeout=20,
        verify=verify_ssl,
    )
    resp.raise_for_status()
    data = resp.json()

    issuer = (data.get("issuer") or "").strip()
    auth_url = (data.get("authorization_endpoint") or "").strip()
    token_url = (data.get("token_endpoint") or "").strip()
    userinfo_url = (data.get("userinfo_endpoint") or "").strip()
    end_session_url = (data.get("end_session_endpoint") or "").strip()

    if not auth_url or not token_url or not userinfo_url:
        raise ValueError("Discovery missing endpoints")

    # rewrite public root -> internal root for server-to-server calls
    # issuer: http://localhost:9000/application/o/authentik/
    # => public_root = http://localhost:9000
    if issuer and "/application/o/" in issuer:
        public_root = issuer.split("/application/o/")[0].rstrip("/")
        internal_root = base_internal.rstrip("/")

        token_url = token_url.replace(public_root, internal_root)
        userinfo_url = userinfo_url.replace(public_root, internal_root)

        # keep auth_url as PUBLIC (browser redirect)
        # but ensure it uses public url from our config
        auth_url = auth_url.replace(public_root, _public_url().rstrip("/"))

        if end_session_url:
            end_session_url = end_session_url.replace(public_root, _public_url().rstrip("/"))

    return {
        "issuer": issuer,
        "authorization_endpoint": auth_url,
        "token_endpoint": token_url,
        "userinfo_endpoint": userinfo_url,
        "end_session_endpoint": end_session_url,
    }


# ------------------------------------------------------------
# Controller
# ------------------------------------------------------------
class AuthentikSSOController(http.Controller):

    # -------------------------
    # Reset / Logout
    # -------------------------
    @http.route("/auth/authentik/reset", type="http", auth="none", csrf=False, sitemap=False)
    def authentik_reset(self, **kw):
        """Clear local Odoo session and redirect to login page."""
        _logout_local_session()
        resp = redirect("/web/login", code=303)

        # force browser drop cookie
        resp.set_cookie("session_id", "", expires=0, max_age=0)

        return resp

    @http.route("/auth/authentik/logout", type="http", auth="none", csrf=False, sitemap=False)
    def authentik_logout(self, **kw):
        """
        Logout local Odoo session and optionally logout from Authentik too.
        """
        _ensure_db()

        slug = _oidc_slug()
        verify_ssl = _verify_ssl()
        base_internal = _internal_url()

        end_session_url = ""
        try:
            endpoints = _discover_endpoints(base_internal, slug, verify_ssl=verify_ssl)
            end_session_url = endpoints.get("end_session_endpoint") or ""
        except Exception:
            _logger.exception("Discovery failed for logout (ignored)")

        _logout_local_session()

        # If user wants full SSO logout, redirect to authentik end-session
        # You can disable by setting authentik.logout_sso=0
        if _as_bool(_cfg("authentik.logout_sso", "1")) and end_session_url:
            # post_logout_redirect_uri must be public URL
            post_logout_redirect = f"{_odoo_base_url()}/web/login"
            url = end_session_url + "?" + urllib.parse.urlencode({
                "post_logout_redirect_uri": post_logout_redirect,
            })
            resp = redirect(url, code=303)
        else:
            resp = redirect("/web/login", code=303)

        resp.set_cookie("session_id", "", expires=0, max_age=0)
        return resp

    # -------------------------
    # Login
    # -------------------------
    @http.route("/auth/authentik/login", type="http", auth="public", website=True, csrf=False)
    def authentik_login(self, **kw):
        enabled = _as_bool(_cfg("authentik.enabled", "1"))
        if not enabled:
            return redirect("/web/login?error=authentik_disabled", code=303)

        client_id = (_cfg("authentik.client_id") or "").strip()
        scope = (_cfg("authentik.scope") or "openid profile email").strip()

        if not client_id:
            _logger.error("Missing authentik.client_id")
            return redirect("/web/login?error=authentik_missing_client_id", code=303)

        slug = _oidc_slug()
        if not slug:
            _logger.error("Missing authentik.slug" + slug)
            return redirect("/web/login?error=missing_slug", code=303)

        # IMPORTANT: clear old/broken session to avoid 403
        _logout_local_session()

        odoo_base = _odoo_base_url()
        redirect_uri = f"{odoo_base}/auth/authentik/callback"

        base_internal = _internal_url()
        verify_ssl = _verify_ssl()

        try:
            endpoints = _discover_endpoints(base_internal, slug, verify_ssl=verify_ssl)
        except Exception:
            _logger.exception("OIDC discovery failed")
            return redirect("/web/login?error=discovery_failed", code=303)

        authorize_url = endpoints["authorization_endpoint"]

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        request.session["authentik_state"] = state
        request.session["authentik_nonce"] = nonce

        params = {
            "client_id": client_id,
            "response_type": "code",
            "scope": scope,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
        }

        url = authorize_url + "?" + urllib.parse.urlencode(params)

        _logger.warning("Redirecting to Authentik authorize: %s", url)
        return redirect(url, code=303)

    # -------------------------
    # Callback
    # -------------------------
    @http.route("/auth/authentik/callback", type="http", auth="public", website=True, csrf=False)
    def authentik_callback(self, code=None, state=None, error=None, error_description=None, **kw):
        _ensure_db()

        if error:
            _logger.warning("Authentik callback error=%s desc=%s", error, error_description)
            return redirect("/web/login?error=authentik_oidc_error", code=303)

        if not code:
            _logger.warning("Authentik callback missing code")
            return redirect("/web/login?error=missing_code", code=303)

        session_state = request.session.get("authentik_state")
        if not state or not session_state or state != session_state:
            _logger.warning("Invalid state: got=%s expected=%s", state, session_state)
            return redirect("/web/login?error=invalid_state", code=303)

        slug = _oidc_slug()
        client_id = (_cfg("authentik.client_id") or "").strip()
        client_secret = (_cfg("authentik.client_secret") or "").strip()

        if not slug or not client_id or not client_secret:
            _logger.error("Missing config: authentik.slug / authentik.client_id / authentik.client_secret")
            return redirect("/web/login?error=missing_config", code=303)

        odoo_base = _odoo_base_url()
        redirect_uri = f"{odoo_base}/auth/authentik/callback"

        base_internal = _internal_url()
        verify_ssl = _verify_ssl()

        # discover endpoints (token/userinfo internal rewritten)
        try:
            endpoints = _discover_endpoints(base_internal, slug, verify_ssl=verify_ssl)
        except Exception:
            _logger.exception("OIDC discovery failed")
            return redirect("/web/login?error=discovery_failed", code=303)

        token_url = endpoints["token_endpoint"]
        userinfo_url = endpoints["userinfo_endpoint"]

        _logger.info("Authentik endpoints: token=%s userinfo=%s", token_url, userinfo_url)

        # 1) Exchange code -> token
        token_resp = None
        try:
            token_resp = requests.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                timeout=30,
                verify=verify_ssl,
            )
            _logger.info("Token exchange status=%s body=%s", token_resp.status_code, token_resp.text[:500])
            token_resp.raise_for_status()
            token_data = token_resp.json()
        except Exception as e:
            _logger.error(
                "Token exchange failed url=%s status=%s body=%s",
                token_url,
                getattr(token_resp, "status_code", None),
                (getattr(token_resp, "text", "") or "")[:2000],
            )
            _logger.exception("Token exchange exception: %s", e)
            return redirect("/web/login?error=token_exchange_failed", code=303)

        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")
        if not access_token:
            _logger.error("No access_token in token response: %s", token_data)
            return redirect("/web/login?error=no_access_token", code=303)

        request.session["authentik_access_token"] = access_token
        if id_token:
            request.session["authentik_id_token"] = id_token

        # 2) Userinfo
        try:
            userinfo_resp = requests.get(
                userinfo_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=30,
                verify=verify_ssl,
            )
            _logger.info("Userinfo status=%s body=%s", userinfo_resp.status_code, userinfo_resp.text[:500])
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()
        except Exception as e:
            _logger.exception("Userinfo failed: %s", e)
            return redirect("/web/login?error=userinfo_failed", code=303)

        request.session["authentik_userinfo"] = userinfo

        sub = userinfo.get("sub")
        email = (userinfo.get("email") or "").strip().lower()
        name = userinfo.get("name") or userinfo.get("preferred_username") or email

        if not sub or not email:
            _logger.error("Invalid userinfo: %s", userinfo)
            return redirect("/web/login?error=invalid_userinfo", code=303)

        Users = request.env["res.users"].sudo()

        user = Users.search([("authentik_sub", "=", sub)], limit=1)
        if not user:
            user = Users.search(["|", ("login", "=", email), ("email", "=", email)], limit=1)

        auto_create = _as_bool(_cfg("authentik.auto_create_user", "1"))

        if not user:
            if not auto_create:
                return redirect("/web/login?error=user_not_allowed", code=303)

            user = Users.create({
                "name": name,
                "login": email,
                "email": email,
                "authentik_sub": sub,
            })
        else:
            # bind sub if missing
            if not user.authentik_sub:
                user.write({"authentik_sub": sub})

        # 3) Establish valid Odoo session (avoid 403)
        try:
            request.session.logout(keep_db=True)
        except Exception:
            pass

        _odoo_login_user(user)

        resp = redirect("/web", code=303)

        # force save
        request.session.modified = True

        _logger.warning("[CALLBACK END] uid=%s sid=%s token=%s Set-Cookie=%s",
                        request.session.uid,
                        getattr(request.session, "sid", None),
                        getattr(request.session, "session_token", None),
                        resp.headers.get("Set-Cookie"))

        return resp

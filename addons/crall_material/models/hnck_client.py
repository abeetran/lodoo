import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from urllib.parse import urlsplit

import requests

from odoo import _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

TOKEN_PATH = "supplier/token"
MERGE_PATH = "supplier/facilities/merge"
TOKEN_SAFETY_MARGIN = 60


def get_setting(env, key, environ_names, default=None):
    value = env["ir.config_parameter"].sudo().get_param(key)
    if value not in (None, ""):
        return value
    if isinstance(environ_names, str):
        environ_names = [environ_names]
    for environ_name in environ_names:
        value = os.environ.get(environ_name)
        if value not in (None, ""):
            return value
    return default


class HnckClient:
    """Client for HNCK_API with a cached bearer token.

    The token is cached server-side (ir.config_parameter) together with its
    expiry timestamp. Every request goes through get_token(), which reuses
    the cached token while valid and fetches a new one otherwise.
    Configuration comes from ir.config_parameter first, then os.environ.
    """

    def __init__(self, env):
        self.env = env

    def base_url(self):
        base = (
            get_setting(
                self.env,
                "crall_material.hnck_api_base",
                ["HNCK_API_URL", "HNCK_API"],
                "https://ncc-api.hanoicheck.com.vn/api/",
            )
            or ""
        ).strip()
        if not base:
            raise UserError(
                _(
                    "Chưa cấu hình HNCK API base URL "
                    "(biến HNCK_API_URL trong .env hoặc Settings)."
                )
            )
        if "://" not in base:
            raise UserError(
                _("HNCK API base URL thiếu schema http/https: %s") % base
            )
        return base.rstrip("/") + "/"

    def get_token(self):
        parameters = self.env["ir.config_parameter"].sudo()
        token = parameters.get_param("crall_material.hnck_access_token")
        try:
            expires_at = float(
                parameters.get_param("crall_material.hnck_token_expires_at") or 0
            )
        except (TypeError, ValueError):
            expires_at = 0
        if token and expires_at - TOKEN_SAFETY_MARGIN > time.time():
            return token
        return self.refresh_token()

    def refresh_token(self):
        url = self.base_url() + TOKEN_PATH
        payload = {
            "grant_type": get_setting(
                self.env,
                "crall_material.hnck_grant_type",
                ["GRANT_TYPE", "HNCK_GRANT_TYPE"],
                "client_credentials",
            ),
            "client_id": get_setting(
                self.env,
                "crall_material.hnck_client_id",
                ["CLIENT_ID", "HNCK_CLIENT_ID"],
            )
            or "",
            "client_secret": get_setting(
                self.env,
                "crall_material.hnck_client_secret",
                ["CLIENT_SECRET", "HNCK_CLIENT_SECRET"],
            )
            or "",
        }
        try:
            response = requests.post(url, data=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as error:
            _logger.exception("Could not fetch HNCK token")
            raise UserError(_("Không thể lấy HNCK token: %s") % error) from error
        except ValueError as error:
            raise UserError(
                _("HNCK token API trả về dữ liệu không phải JSON.")
            ) from error
        if not isinstance(data, dict) or not data.get("access_token"):
            raise UserError(_("HNCK token API không trả về access_token."))
        try:
            expires_in = int(data.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600
        token_type = data.get("token_type") or "Bearer"
        access_token = data["access_token"]
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("crall_material.hnck_access_token", access_token)
        parameters.set_param("crall_material.hnck_token_type", token_type)
        parameters.set_param(
            "crall_material.hnck_token_expires_at", str(time.time() + expires_in)
        )
        _logger.info("Fetched new HNCK access token (expires in %ss)", expires_in)
        return access_token

    def auth_headers(self):
        token = self.get_token()
        if token.lower().startswith("bearer "):
            return {"Authorization": token}
        token_type = (
            get_setting(
                self.env, "crall_material.hnck_token_type", "HNCK_TOKEN_TYPE", "Bearer"
            )
            or "Bearer"
        )
        return {"Authorization": "%s %s" % (token_type, token)}

    @staticmethod
    def timestamp():
        return str(int(time.time()))

    @staticmethod
    def new_nonce(nbytes=12):
        return secrets.token_hex(nbytes)

    def signature(self, method, path, timestamp, nonce, body_bytes):
        secret = (
            get_setting(
                self.env, "crall_material.hnck_hmac_secret", "HMAC_SECRET"
            )
            or ""
        )
        if not secret:
            raise UserError(_("Chưa cấu hình HMAC secret (HNCK_API)."))
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        canonical = "\n".join(
            [method.upper(), path, timestamp, nonce, body_hash]
        )
        digest = hmac.new(
            secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.b64encode(digest).decode("ascii")

    def merge_facilities(self, records):
        body_text = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
        body_bytes = body_text.encode("utf-8")
        url = self.base_url() + MERGE_PATH
        timestamp = self.timestamp()
        nonce = self.new_nonce()
        headers = {
            **self.auth_headers(),
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": self.signature(
                "POST", urlsplit(url).path, timestamp, nonce, body_bytes
            ),
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                url, data=body_text.encode("utf-8"), headers=headers, timeout=30
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as error:
            _logger.exception("HNCK facilities merge failed")
            raise UserError(
                _(
                    "Gọi HNCK merge thất bại: %s\n"
                    "X-Timestamp: %s\nX-Nonce: %s\nX-Signature: %s"
                )
                % (
                    error,
                    headers["X-Timestamp"],
                    headers["X-Nonce"],
                    headers["X-Signature"],
                )
            ) from error
        try:
            return response.json()
        except ValueError:
            return {"raw": (response.text or "")[:500]}

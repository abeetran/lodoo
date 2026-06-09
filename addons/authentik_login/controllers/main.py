import os
import logging
import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

AUTHENTIK_URL = os.environ.get(
    "AUTHENTIK_URL",
    "https://authentikserver.bms360.cloud"
)

AUTHENTIK_TOKEN = os.environ.get(
    "AUTHENTIK_TOKEN",
    ""
)


class AuthentikLogin(http.Controller):

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
            _logger.exception(
                "Authentik Login Error"
            )
            return False

    @http.route(
        "/authentik/login",
        auth="public",
        type="http",
        methods=["POST"],
        csrf=True
    )
    def login(self, **post):

        email = post.get("email")
        password = post.get("password")

        if not email:
            return request.redirect(
                "/web/login"
            )

        result = self._authenticate(
            email,
            password
        )

        if not result:
            return request.redirect(
                "/web/login?error=1"
            )

        Users = request.env[
            "res.users"
        ].sudo()

        user = Users.search(
            [
                ("login", "=", email)
            ],
            limit=1
        )

        if not user:

            user = Users.create(
                {
                    "name": result.get(
                        "name",
                        email
                    ),
                    "login": email,
                    "email": email,
                    "password": password,
                    "authentik_uid": result.get(
                        "id"
                    ),
                    "authentik_email": email,
                }
            )

        else:

            user.write(
                {
                    "password": password,
                    "authentik_uid": result.get(
                        "id"
                    ),
                    "authentik_email": email,
                }
            )

        # chuyển về login chuẩn của Odoo
        return request.redirect(
            "/web/login?login=%s" % email
        )
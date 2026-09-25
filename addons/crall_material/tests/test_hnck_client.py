import json
import time
from email.utils import formatdate
from unittest.mock import patch

import requests

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.crall_material.models.hnck_client import HnckClient


class _FakeRequest:
    def __init__(self, headers):
        self.headers = dict(headers or {})


class _FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code, text="", payload=None, headers=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self.headers = dict(headers or {})
        self.request = _FakeRequest(headers)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                "401 Client Error: Unauthorized for url",
                response=self,
            )

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _valid_token_params(icp, token="stale-token"):
    icp.set_param("crall_material.hnck_api_base", "https://example.com/api/")
    icp.set_param("crall_material.hnck_access_token", token)
    icp.set_param("crall_material.hnck_token_type", "Bearer")
    icp.set_param("crall_material.hnck_token_expires_at", str(time.time() + 3600))
    icp.set_param("crall_material.hnck_hmac_secret", "s3cret")


class TestHnckClientAuth(TransactionCase):
    def test_signature_ignores_surrounding_whitespace_in_secret(self):
        icp = self.env["ir.config_parameter"].sudo()
        client = HnckClient(self.env)
        body = b"{}"
        icp.set_param("crall_material.hnck_hmac_secret", "s3cret")
        expected = client.signature(
            "POST", "/api/supplier/dishes/merge", "1790044905", "nonce", body
        )
        icp.set_param("crall_material.hnck_hmac_secret", "  s3cret\n")
        self.assertEqual(
            expected,
            client.signature(
                "POST", "/api/supplier/dishes/merge", "1790044905", "nonce", body
            ),
        )

    def test_signed_post_refreshes_token_once_on_401(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)
        calls = []

        def fake_post(url, data=None, headers=None, timeout=None):
            calls.append(dict(headers or {}))
            if len(calls) == 1:
                return _FakeResponse(
                    401,
                    text='{"message":"Unauthenticated."}',
                    headers=headers,
                )
            return _FakeResponse(200, payload={"ok": True}, headers=headers)

        def fake_refresh(inner_self):
            icp.set_param("crall_material.hnck_access_token", "fresh-token")
            icp.set_param(
                "crall_material.hnck_token_expires_at", str(time.time() + 3600)
            )
            return "fresh-token"

        post_path = (
            "odoo.addons.crall_material.models.hnck_client.requests.post"
        )
        with (
            patch(post_path, side_effect=fake_post),
            patch.object(HnckClient, "refresh_token", fake_refresh),
        ):
            result = HnckClient(self.env).push_supplier_dishes(
                [{"ma_mon_an": "M1"}]
            )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 2)
        self.assertIn("stale-token", calls[0]["Authorization"])
        self.assertIn("fresh-token", calls[1]["Authorization"])

    def test_timestamp_follows_synced_clock_offset(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)
        client = HnckClient(self.env)
        server_now = time.time() + 3600  # HNCK nhanh hơn local 1 giờ
        response = _FakeResponse(
            200,
            headers={"Date": formatdate(server_now, usegmt=True)},
        )
        offset = client.sync_clock_from_response(response)
        self.assertAlmostEqual(offset, 3600, delta=5)
        self.assertAlmostEqual(
            int(client.timestamp()) - server_now, 0, delta=5
        )

    def test_signed_post_retries_expired_timestamp_with_corrected_clock(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)
        server_now = time.time() + 3600
        calls = []

        def fake_post(url, data=None, headers=None, timeout=None):
            calls.append(dict(headers or {}))
            if len(calls) == 1:
                return _FakeResponse(
                    401,
                    text='{"success":false,"message":"Timestamp hết hạn.",'
                    '"error_code":"EXPIRED_TIMESTAMP"}',
                    headers={
                        **dict(headers or {}),
                        "Date": formatdate(server_now, usegmt=True),
                    },
                )
            return _FakeResponse(200, payload={"ok": True}, headers=headers)

        def fake_refresh(inner_self):
            return "fresh-token"

        post_path = (
            "odoo.addons.crall_material.models.hnck_client.requests.post"
        )
        with (
            patch(post_path, side_effect=fake_post),
            patch.object(HnckClient, "refresh_token", fake_refresh),
        ):
            result = HnckClient(self.env).push_supplier_dishes(
                [{"ma_mon_an": "M1"}]
            )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 2)
        # Lần thử lại phải ký timestamp theo giờ HNCK, không phải giờ local.
        self.assertAlmostEqual(
            int(calls[1]["X-Timestamp"]) - server_now, 0, delta=10
        )

    def test_each_request_uses_fresh_timestamp_and_nonce(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)
        calls = []

        def fake_post(url, data=None, headers=None, timeout=None):
            calls.append(dict(headers or {}))
            return _FakeResponse(200, payload={"ok": True}, headers=headers)

        post_path = (
            "odoo.addons.crall_material.models.hnck_client.requests.post"
        )
        windows = []
        with patch(post_path, side_effect=fake_post):
            client = HnckClient(self.env)
            for records in (
                [{"ma_mon_an": "M1"}],
                [{"ma_mon_an": "M2"}],
            ):
                before = time.time()
                client.push_supplier_dishes(records)
                windows.append((before, time.time()))
            before = time.time()
            client.merge_facilities([{"ma_co_so": "S1"}])
            windows.append((before, time.time()))
        self.assertEqual(len(calls), 3)
        nonces = [call["X-Nonce"] for call in calls]
        self.assertEqual(len(set(nonces)), 3)
        for (before, after), call in zip(windows, calls):
            sent = int(call["X-Timestamp"])
            self.assertGreaterEqual(sent, int(before) - 1)
            self.assertLessEqual(sent, int(after) + 1)

    def test_signed_post_error_includes_server_body(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)

        def fake_post(url, data=None, headers=None, timeout=None):
            return _FakeResponse(
                401, text="invalid signature", headers=headers
            )

        def fake_refresh(inner_self):
            return "fresh-token"

        post_path = (
            "odoo.addons.crall_material.models.hnck_client.requests.post"
        )
        with (
            patch(post_path, side_effect=fake_post),
            patch.object(HnckClient, "refresh_token", fake_refresh),
            self.assertRaises(UserError) as ctx,
        ):
            HnckClient(self.env).push_supplier_dishes([{"ma_mon_an": "M1"}])
        self.assertIn("invalid signature", str(ctx.exception))


class TestPushSupplierSteps(TransactionCase):
    def test_push_steps_posts_signed_body(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)
        calls = []

        def fake_post(url, data=None, headers=None, timeout=None):
            calls.append(
                {
                    "url": url,
                    "body": json.loads(data.decode("utf-8")),
                    "headers": dict(headers or {}),
                }
            )
            return _FakeResponse(200, payload={"ok": True}, headers=headers)

        post_path = (
            "odoo.addons.crall_material.models.hnck_client.requests.post"
        )
        with patch(post_path, side_effect=fake_post):
            result = HnckClient(self.env).push_supplier_steps(
                [{"ma_khau": "K1", "ten_khau": "Sơ chế"}]
            )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["url"].endswith("supplier/steps/merge"))
        self.assertEqual(
            calls[0]["body"], [{"ma_khau": "K1", "ten_khau": "Sơ chế"}]
        )
        headers = calls[0]["headers"]
        self.assertIn("stale-token", headers["Authorization"])
        for key in ("X-Timestamp", "X-Nonce", "X-Signature"):
            self.assertIn(key, headers)

    def test_push_steps_refreshes_expired_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp, token="expired-token")
        icp.set_param(
            "crall_material.hnck_token_expires_at", str(time.time() - 10)
        )
        calls = []

        def fake_post(url, data=None, headers=None, timeout=None):
            calls.append(dict(headers or {}))
            return _FakeResponse(200, payload={"ok": True}, headers=headers)

        def fake_refresh(inner_self):
            icp.set_param("crall_material.hnck_access_token", "fresh-token")
            icp.set_param(
                "crall_material.hnck_token_expires_at", str(time.time() + 3600)
            )
            return "fresh-token"

        post_path = (
            "odoo.addons.crall_material.models.hnck_client.requests.post"
        )
        with (
            patch(post_path, side_effect=fake_post),
            patch.object(HnckClient, "refresh_token", fake_refresh),
        ):
            HnckClient(self.env).push_supplier_steps(
                [{"ma_khau": "K1", "ten_khau": "Sơ chế"}]
            )
        self.assertEqual(len(calls), 1)
        self.assertIn("fresh-token", calls[0]["Authorization"])

    def test_push_steps_empty_raises(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)
        with self.assertRaises(UserError):
            HnckClient(self.env).push_supplier_steps([])


class TestPushSupplierProcesses(TransactionCase):
    def test_push_processes_posts_signed_body(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)
        calls = []

        def fake_post(url, data=None, headers=None, timeout=None):
            calls.append(
                {
                    "url": url,
                    "body": json.loads(data.decode("utf-8")),
                    "headers": dict(headers or {}),
                }
            )
            return _FakeResponse(200, payload={"ok": True}, headers=headers)

        post_path = (
            "odoo.addons.crall_material.models.hnck_client.requests.post"
        )
        payload = [
            {
                "ma_quy_trinh": "QT001",
                "ten_quy_trinh": "Quy trình chế biến thịt heo",
                "loai_san_pham": "food",
                "danh_sach_khau": [
                    {"ma_khau": "SO_CHE", "thu_tu": 1},
                    {"ma_khau": "CHE_BIEN", "thu_tu": 2},
                    {"ma_khau": "DONG_GOI", "thu_tu": 3},
                ],
            }
        ]
        with patch(post_path, side_effect=fake_post):
            result = HnckClient(self.env).push_supplier_processes(payload)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["url"].endswith("supplier/processes/merge"))
        self.assertEqual(calls[0]["body"], payload)
        headers = calls[0]["headers"]
        self.assertIn("stale-token", headers["Authorization"])
        for key in ("X-Timestamp", "X-Nonce", "X-Signature"):
            self.assertIn(key, headers)

    def test_push_processes_refreshes_expired_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp, token="expired-token")
        icp.set_param(
            "crall_material.hnck_token_expires_at", str(time.time() - 10)
        )
        calls = []

        def fake_post(url, data=None, headers=None, timeout=None):
            calls.append(dict(headers or {}))
            return _FakeResponse(200, payload={"ok": True}, headers=headers)

        def fake_refresh(inner_self):
            icp.set_param("crall_material.hnck_access_token", "fresh-token")
            icp.set_param(
                "crall_material.hnck_token_expires_at", str(time.time() + 3600)
            )
            return "fresh-token"

        post_path = (
            "odoo.addons.crall_material.models.hnck_client.requests.post"
        )
        with (
            patch(post_path, side_effect=fake_post),
            patch.object(HnckClient, "refresh_token", fake_refresh),
        ):
            HnckClient(self.env).push_supplier_processes(
                [{"ma_quy_trinh": "QT001"}]
            )
        self.assertEqual(len(calls), 1)
        self.assertIn("fresh-token", calls[0]["Authorization"])

    def test_push_processes_empty_raises(self):
        icp = self.env["ir.config_parameter"].sudo()
        _valid_token_params(icp)
        with self.assertRaises(UserError):
            HnckClient(self.env).push_supplier_processes([])

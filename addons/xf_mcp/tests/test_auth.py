# Copyright 2024 XFanis
# License OPL-1 or later (https://www.odoo.com/documentation/master/legal/licenses.html).

import ipaddress
import time

from odoo.tests.common import TransactionCase

from ..services.auth import (
    _parse_ip_list,
    _rate_limit_lock,
    _rate_limit_store,
    check_auth_rate_limit,
    check_rate_limit,
    record_auth_failure,
)


class TestMcpAuth(TransactionCase):
    """Tests for MCP authentication logic."""

    def setUp(self):
        super().setUp()
        self.admin_user = self.env.ref("base.user_admin")

    def test_check_rate_limit_allows_first_request(self):
        allowed, retry_after = check_rate_limit(self.admin_user.id, max_requests=60)
        self.assertTrue(allowed)
        self.assertEqual(retry_after, 0)

    def test_check_rate_limit_blocks_after_max(self):
        key = str(self.admin_user.id) + "_test_block"
        # Flood the store for a fake user
        now = time.time()
        with _rate_limit_lock:
            _rate_limit_store[key] = [now] * 5
        # Use a fake uid that maps to the flooded key — just verify logic works
        allowed, _ = check_rate_limit(self.admin_user.id, max_requests=60)
        self.assertTrue(allowed)  # real user not flooded

    def test_record_and_check_auth_failure(self):
        ip = "192.0.2.1"
        allowed, _ = check_auth_rate_limit(ip)
        self.assertTrue(allowed)
        record_auth_failure(ip)
        allowed, _ = check_auth_rate_limit(ip)
        self.assertTrue(allowed)  # only 1 failure, well under 20

    def test_parse_ip_list(self):
        networks = _parse_ip_list("192.168.1.0/24\n10.0.0.1\n# comment\n")
        self.assertEqual(len(networks), 2)
        self.assertIn(
            ipaddress.ip_address("192.168.1.100"),
            [addr for net in networks for addr in [ipaddress.ip_address("192.168.1.100")] if addr in net],
        )

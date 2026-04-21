import ipaddress
import logging
import threading
import time

from odoo.exceptions import AccessDenied
from odoo.tools.convert import str2bool

# AccessDenied strings are technical auth messages, not translated UI text
# pylint: disable=translation-required

_logger = logging.getLogger(__name__)

# Thread-safe rate limiting stores
_rate_limit_store = {}
_rate_limit_lock = threading.Lock()
_auth_fail_store = {}
_auth_fail_lock = threading.Lock()

RATE_LIMIT_WINDOW = 60  # seconds
AUTH_FAIL_WINDOW = 300  # 5 minutes
AUTH_FAIL_MAX = 20


def authenticate_request(request):
    """Authenticate an MCP request. Returns (uid, user recordset, db_name).

    Supports:
    - Bearer token (API key): Authorization: Bearer <key>
    """
    # Support ?db= query parameter for multi-database setups
    db_name = request.httprequest.args.get("db") or getattr(request, "db", None) or request.session.db
    if not db_name:
        raise AccessDenied("No database selected. Use ?db=<name> query parameter.")

    auth_header = request.httprequest.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        return _authenticate_api_key(request, token, db_name)

    raise AccessDenied("Missing or unsupported Authorization header. Use Bearer token.")


def _authenticate_api_key(request, api_key, db_name):
    """Validate API key via res.users.apikeys."""
    env = request.env
    try:
        uid = env["res.users.apikeys"]._check_credentials(scope="rpc", key=api_key)
    except AccessDenied:
        uid = None

    if not uid:
        _logger.warning("MCP auth failed: invalid API key (key length: %d chars)", len(api_key) if api_key else 0)
        raise AccessDenied("Invalid API key.")

    user = env["res.users"].sudo().browse(uid)
    if not user.exists() or not user.active:
        raise AccessDenied("User account is inactive.")

    return uid, user, db_name


def check_rate_limit(user_id, max_requests):
    """Check per-user rate limit. Returns (allowed, retry_after_seconds)."""
    now = time.time()
    key = str(user_id)

    with _rate_limit_lock:
        timestamps = _rate_limit_store.get(key, [])
        # Remove old entries outside the window
        timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]

        if len(timestamps) >= max_requests:
            retry_after = RATE_LIMIT_WINDOW - (now - timestamps[0])
            _rate_limit_store[key] = timestamps
            return False, max(1, int(retry_after))

        timestamps.append(now)
        _rate_limit_store[key] = timestamps
        return True, 0


def check_auth_rate_limit(ip_address):
    """Check auth failure rate per IP. Returns (allowed, retry_after_seconds)."""
    now = time.time()

    with _auth_fail_lock:
        timestamps = _auth_fail_store.get(ip_address, [])
        timestamps = [t for t in timestamps if now - t < AUTH_FAIL_WINDOW]
        _auth_fail_store[ip_address] = timestamps

        if len(timestamps) >= AUTH_FAIL_MAX:
            retry_after = AUTH_FAIL_WINDOW - (now - timestamps[0])
            return False, max(1, int(retry_after))

        return True, 0


def record_auth_failure(ip_address):
    """Record a failed auth attempt for brute force protection."""
    with _auth_fail_lock:
        timestamps = _auth_fail_store.get(ip_address, [])
        timestamps.append(time.time())
        _auth_fail_store[ip_address] = timestamps


def check_ip_filtering(request, env):
    """Check IP filtering rules. Returns True if allowed."""
    enabled = env["ir.config_parameter"].sudo().get_param("xf_mcp.ip_filtering_enabled", "False")
    if not str2bool(enabled):
        return True

    strategy = env["ir.config_parameter"].sudo().get_param("xf_mcp.ip_filtering_strategy", "allow_list")
    ip_list_raw = env["ir.config_parameter"].sudo().get_param("xf_mcp.ip_list", "")

    if not ip_list_raw or not ip_list_raw.strip():
        # No IPs configured: allow_list with empty list = block all, deny_list with empty = allow all
        return strategy != "allow_list"

    client_ip = get_client_ip(request)
    try:
        client_addr = ipaddress.ip_address(client_ip)
    except ValueError:
        _logger.warning("MCP: could not parse client IP '%s'", client_ip)
        return False

    networks = _parse_ip_list(ip_list_raw)
    ip_in_list = any(client_addr in network for network in networks)

    if strategy == "allow_list":
        return ip_in_list
    # deny_list
    return not ip_in_list


def _parse_ip_list(raw):
    """Parse IP list text (one entry per line) into list of ip_network objects."""
    networks = []
    for line in raw.strip().splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        try:
            # Handles both single IPs and CIDR masks
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            _logger.warning("MCP: invalid IP entry '%s', skipping", entry)
    return networks


def get_client_ip(request):
    """Extract client IP from request, respecting trusted proxy headers."""
    # Check forwarded headers only from trusted proxies
    remote_addr = request.httprequest.remote_addr or "127.0.0.1"
    try:
        if ipaddress.ip_address(remote_addr).is_private:
            forwarded = request.httprequest.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
            real_ip = request.httprequest.headers.get("X-Real-IP", "")
            if real_ip:
                return real_ip.strip()
    except ValueError:  # pylint: disable=except-pass
        pass
    return remote_addr


def get_user_agent(request):
    """Extract user agent string from request."""
    return request.httprequest.headers.get("User-Agent", "")[:500]

# Copyright 2025 XFanis
# License OPL-1 (https://www.odoo.com/documentation/user/legal/licenses.html#odoo-apps).
import logging

from odoo import http

_logger = logging.getLogger(__name__)

_MCP_PATH = "/mcp"


def post_load():
    """Patch Request._post_init to pick up ?db= from query args for /mcp requests.

    Odoo 17 resolves the database exclusively from the session cookie or single-db
    auto-detection inside _get_session_and_dbname().  Multi-db MCP clients that pass
    ?db=NAME in the URL get 404 because the registry is never loaded and the /mcp route
    is not visible in nodb mode.

    After the normal _post_init completes, if no db was resolved but ?db= is present,
    we validate it via http.db_filter (which already respects --db-filter and --database
    config) and set it on the session so the request proceeds via _serve_db().
    """
    _logger.info("xf_mcp: patching Request._post_init to support ?db= on /mcp")

    original_post_init = http.Request._post_init

    def _post_init(self):
        original_post_init(self)
        if not self.db and self.httprequest.path.startswith(_MCP_PATH):
            db = self.httprequest.args.get("db", "").strip()
            if db and http.db_filter([db]):
                self.session.db = db
                self.db = db

    http.Request._post_init = _post_init

import logging

_logger = logging.getLogger(__name__)

_MCP_PATH = "/mcp"


def post_load():
    try:
        from odoo import http

        _logger.info("xf_mcp: patching Request._post_init")

        # tránh crash khi Odoo chưa init xong
        if not hasattr(http, "Request"):
            _logger.warning("Request not ready, skip MCP patch")
            return

        if not hasattr(http.Request, "_post_init"):
            _logger.warning("Request._post_init not found, skip MCP patch")
            return

        original_post_init = http.Request._post_init

        def _post_init(self):
            original_post_init(self)

            if not self.db and self.httprequest.path.startswith(_MCP_PATH):
                db = self.httprequest.args.get("db", "").strip()
                if db and http.db_filter([db]):
                    self.session.db = db
                    self.db = db

        http.Request._post_init = _post_init

    except Exception as e:
        _logger.error("xf_mcp post_load failed: %s", e)
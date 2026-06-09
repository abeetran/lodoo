from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def create(self, vals):
        user = super().create(vals)

        try:
            with self.env.cr.savepoint():
                self.env.cr.execute("""
                    INSERT INTO my_table(name)
                    VALUES (%s)
                """, (vals.get("name"),))
        except Exception as e:
            _logger.exception("Custom SQL Error: %s", e)

        return user
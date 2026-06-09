from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)

        for user in users:
            try:
                with self.env.cr.savepoint():
                    self.env["my.table"].sudo().create({
                        "name": user.name,
                    })
            except Exception:
                _logger.exception(
                    "Error while creating extra record for user %s",
                    user.login
                )

        return users
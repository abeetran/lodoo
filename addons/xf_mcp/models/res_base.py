# Copyright 2024 XFanis
# License OPL-1 or later (https://www.odoo.com/documentation/master/legal/licenses.html).

from odoo import api, models


class Base(models.AbstractModel):
    """Extend the base abstract model with MCP discovery helpers."""

    _inherit = "base"

    @api.model
    def get_methods(self):
        """Return sorted list of public callable methods on this model.

        Used by the MCP method_call tool for discovery:
        call with method='get_methods' and no ids to see available methods.
        """
        return sorted(
            [
                method
                for method in dir(self)
                if not method.startswith("_") and callable(getattr(self.__class__, method, None))
            ]
        )

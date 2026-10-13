from odoo import api, models


class UomUom(models.Model):
    _inherit = "uom.uom"

    PRIORITY_UOM_XMLIDS = (
        "uom.product_uom_gram",
        "uom.product_uom_kgm",
        "set_top_menu.product_uom_milliliter",
        "uom.product_uom_litre",
        "set_top_menu.product_uom_thung",
        "set_top_menu.product_uom_bo",
        "set_top_menu.product_uom_dia",
    )

    @api.model
    def _priority_uom_ids(self):
        ids = []
        for xmlid in self.PRIORITY_UOM_XMLIDS:
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                ids.append(record.id)
        return ids

    @api.model
    # Override name_search (not _name_search: Odoo 17 returns a lazy Query
    # there). The UoM table is tiny so sorting the full match list is cheap.
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        records = super().name_search(name, args, operator, None)
        rank = {
            record_id: index
            for index, record_id in enumerate(self._priority_uom_ids())
        }
        records = sorted(
            records, key=lambda item: rank.get(item[0], len(rank))
        )
        if limit is not None:
            records = records[:limit]
        return records

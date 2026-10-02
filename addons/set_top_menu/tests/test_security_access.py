import csv
import os

from odoo.modules.module import get_module_path
from odoo.tests.common import TransactionCase


class TestSecurityAccessCsv(TransactionCase):
    def test_access_csv_models_resolve(self):
        """Every model_id in ir.model.access.csv must resolve.

        Guards against leftover rows pointing at deleted models, which
        break module upgrade with 'Missing required value for Model'.
        """
        csv_path = os.path.join(
            get_module_path("set_top_menu"),
            "security",
            "ir.model.access.csv",
        )
        with open(csv_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(rows)
        for row in rows:
            model = self.env.ref("set_top_menu.%s" % row["model_id:id"])
            self.assertTrue(model.exists())

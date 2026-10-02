from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval


class TestFoodSourceSeparation(TransactionCase):
    def _upsert(self, items, source):
        return self.env["product.template"]._crall_upsert_foods(
            items, source=source
        )

    def test_foods_sync_does_not_steal_standard_record(self):
        standard = self.env["product.template"].create(
            {
                "name": "Rau",
                "crall_supplier_id": "1",
                "crall_food_source": "standard",
            }
        )
        counts = self._upsert(
            [{"id": 1, "name": "Rau muống"}], source="foods"
        )
        self.assertEqual(
            (counts["created"], counts["updated"], counts["skipped"]),
            (1, 0, 0),
        )
        self.assertEqual(standard.name, "Rau")
        self.assertEqual(standard.crall_food_source, "standard")
        food = self.env["product.template"].search(
            [("crall_food_source", "=", "foods")], limit=1
        )
        self.assertEqual(food.name, "Rau muống")
        self.assertEqual(food.crall_supplier_id, "1")

    def test_foods_sync_updates_own_record(self):
        food = self.env["product.template"].create(
            {
                "name": "Tên cũ",
                "crall_supplier_id": "7",
                "crall_food_source": "foods",
            }
        )
        counts = self._upsert(
            [{"id": 7, "name": "Rau muống"}], source="foods"
        )
        self.assertEqual(
            (counts["created"], counts["updated"], counts["skipped"]),
            (0, 1, 0),
        )
        self.assertEqual(food.name, "Rau muống")
        self.assertEqual(food.crall_food_source, "foods")
        self.assertEqual(
            self.env["product.template"].search_count(
                [("crall_supplier_id", "=", "7")]
            ),
            1,
        )

    def test_standard_sync_does_not_steal_foods_record(self):
        food = self.env["product.template"].create(
            {
                "name": "Rau muống",
                "crall_supplier_id": "1",
                "crall_food_source": "foods",
            }
        )
        counts = self._upsert([{"id": 1, "name": "Rau"}], source="standard")
        self.assertEqual(
            (counts["created"], counts["updated"], counts["skipped"]),
            (1, 0, 0),
        )
        self.assertEqual(food.name, "Rau muống")
        self.assertEqual(food.crall_food_source, "foods")

    def test_standard_list_shows_only_standard_source(self):
        standard = self.env["product.template"].create(
            {
                "name": "Rau",
                "crall_supplier_id": "1",
                "crall_food_source": "standard",
            }
        )
        food = self.env["product.template"].create(
            {
                "name": "Rau muống",
                "crall_supplier_id": "1",
                "crall_food_source": "foods",
            }
        )
        action = self.env.ref("crall_material.action_crall_standard_food_list")
        found_ids = self.env["product.template"].search(
            safe_eval(action.domain)
        ).ids
        self.assertIn(standard.id, found_ids)
        self.assertNotIn(food.id, found_ids)

    def test_foods_default_code_must_be_unique(self):
        self.env["product.template"].create(
            {
                "name": "Rau muống",
                "default_code": "TP-001",
                "crall_food_source": "foods",
            }
        )
        with self.assertRaises(ValidationError):
            self.env["product.template"].create(
                {
                    "name": "Rau muống trùng mã",
                    "default_code": "TP-001",
                    "crall_food_source": "foods",
                }
            )
        other = self.env["product.template"].create(
            {
                "name": "Thịt ba chỉ",
                "default_code": "TP-002",
                "crall_food_source": "foods",
            }
        )
        with self.assertRaises(ValidationError):
            other.write({"default_code": "TP-001"})

    def test_foods_default_code_empty_allowed(self):
        first = self.env["product.template"].create(
            {"name": "Rau không mã 1", "crall_food_source": "foods"}
        )
        second = self.env["product.template"].create(
            {"name": "Rau không mã 2", "crall_food_source": "foods"}
        )
        self.assertFalse(first.default_code)
        self.assertFalse(second.default_code)

    def test_foods_default_code_ignores_other_sources(self):
        self.env["product.template"].create(
            {
                "name": "Rau chuẩn",
                "default_code": "TP-001",
                "crall_supplier_id": "1",
                "crall_food_source": "standard",
            }
        )
        self.env["product.template"].create(
            {"name": "Sản phẩm thường", "default_code": "TP-001"}
        )
        food = self.env["product.template"].create(
            {
                "name": "Rau muống",
                "default_code": "TP-001",
                "crall_food_source": "foods",
            }
        )
        self.assertEqual(food.default_code, "TP-001")

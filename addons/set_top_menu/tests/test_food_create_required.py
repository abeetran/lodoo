from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


MATERIAL_CONTEXT = {
    "default_crall_food_source": "foods",
    "set_top_menu_require_food_fields": True,
}


class TestFoodCreateRequired(TransactionCase):
    def _material_create(self, vals):
        return (
            self.env["product.template"]
            .with_context(**MATERIAL_CONTEXT)
            .create(vals)
        )

    def _process(self):
        return self.env["set_top_menu.production.process"].create(
            {"name": "Quy trình test", "code": "QT-FOOD-REQ"}
        )

    def _standard_food(self):
        return self.env["product.template"].create(
            {
                "name": "Rau chuẩn",
                "crall_supplier_id": "STD-REQ",
                "crall_food_source": "standard",
            }
        )

    def _full_vals(self):
        return {
            "name": "Rau muống",
            "default_code": "TP-REQ-001",
            "crall_standard_food_id": self._standard_food().id,
            "process_ids": [(6, 0, [self._process().id])],
        }

    def test_material_create_lists_all_missing_fields(self):
        with self.assertRaises(ValidationError) as raised:
            self._material_create({})
        message = str(raised.exception)
        for label in (
            "Tên",
            "Danh mục thực phẩm chuẩn",
            "Quy trình sản xuất",
            "Mã tham chiếu nội bộ",
        ):
            self.assertIn(label, message)

    def test_material_create_lists_only_missing_fields(self):
        vals = self._full_vals()
        del vals["default_code"]
        with self.assertRaises(ValidationError) as raised:
            self._material_create(vals)
        self.assertIn("Mã tham chiếu nội bộ", str(raised.exception))

    def test_material_create_full_passes(self):
        food = self._material_create(self._full_vals())
        self.assertEqual(food.crall_food_source, "foods")
        self.assertEqual(len(food.process_ids), 1)

    def test_create_without_flag_skips_check(self):
        food = self.env["product.template"].create(
            {"name": "Thực phẩm sync", "crall_food_source": "foods"}
        )
        self.assertFalse(food.default_code)

    def test_write_legacy_record_not_blocked(self):
        food = self.env["product.template"].create(
            {"name": "Thực phẩm cũ", "crall_food_source": "foods"}
        )
        food.with_context(**MATERIAL_CONTEXT).write({"name": "Tên mới"})
        self.assertEqual(food.name, "Tên mới")

    def test_copy_skips_check(self):
        food = self.env["product.template"].create(
            {"name": "Thực phẩm gốc", "crall_food_source": "foods"}
        )
        dupe = food.with_context(**MATERIAL_CONTEXT).copy()
        self.assertTrue(dupe.exists())

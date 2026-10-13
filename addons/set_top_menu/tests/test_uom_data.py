from odoo.tests.common import TransactionCase


class TestUomData(TransactionCase):
    def test_catering_uoms_available(self):
        ml = self.env.ref("set_top_menu.product_uom_milliliter")
        case = self.env.ref("set_top_menu.product_uom_thung")
        combo = self.env.ref("set_top_menu.product_uom_bo")
        plate = self.env.ref("set_top_menu.product_uom_dia")
        self.assertTrue(ml.active)
        self.assertTrue(case.active)
        self.assertTrue(combo.active)
        self.assertTrue(plate.active)
        litre = self.env.ref("uom.product_uom_litre")
        self.assertEqual(ml.category_id, litre.category_id)
        self.assertEqual(ml.uom_type, "smaller")
        self.assertAlmostEqual(ml._compute_quantity(1000.0, litre), 1.0)
        self.assertAlmostEqual(litre._compute_quantity(2.0, ml), 2000.0)
        unit = self.env.ref("uom.product_uom_unit")
        categories = {
            case.category_id.id,
            combo.category_id.id,
            plate.category_id.id,
            unit.category_id.id,
        }
        self.assertEqual(len(categories), 4)
        for each in (case, combo, plate):
            self.assertEqual(each.uom_type, "reference")
            self.assertEqual(each.factor, 1.0)

    def test_core_weight_volume_uoms_available(self):
        for xmlid in (
            "uom.product_uom_gram",
            "uom.product_uom_kgm",
            "uom.product_uom_litre",
        ):
            self.assertTrue(self.env.ref(xmlid).active)

    def test_priority_uoms_first(self):
        expected = [
            self.env.ref(xmlid).id
            for xmlid in (
                "uom.product_uom_gram",
                "uom.product_uom_kgm",
                "set_top_menu.product_uom_milliliter",
                "uom.product_uom_litre",
                "set_top_menu.product_uom_thung",
                "set_top_menu.product_uom_bo",
                "set_top_menu.product_uom_dia",
            )
        ]
        found = [
            record_id
            for record_id, _name in self.env["uom.uom"].name_search(
                "", limit=20
            )
        ]
        self.assertEqual(found[:7], expected)
        short = [
            record_id
            for record_id, _name in self.env["uom.uom"].name_search("", limit=5)
        ]
        self.assertEqual(short, expected[:5])

    def test_priority_uom_first_on_typed_search(self):
        found = [
            record_id
            for record_id, _name in self.env["uom.uom"].name_search("thùng")
        ]
        self.assertEqual(
            found[0], self.env.ref("set_top_menu.product_uom_thung").id
        )

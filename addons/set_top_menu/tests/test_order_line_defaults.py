import xml.etree.ElementTree as ET
from ast import literal_eval

from odoo.tests.common import TransactionCase


class TestOrderLineDefaults(TransactionCase):
    def _order(self, reference="DH-DEF-001"):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )

    def _template(self, name, price):
        return self.env["product.template"].create(
            {"name": name, "list_price": price}
        )

    def _dish(self, code, sale_price=45000.0):
        uom = self.env.ref("uom.product_uom_unit")
        return self.env["set_top_menu.menu.item"].create(
            {
                "name": "Món %s" % code,
                "item_code": code,
                "serving_size": 1.0,
                "serving_uom_id": uom.id,
                "sale_price": sale_price,
            }
        )

    def test_template_syncs_dish_price_and_uom(self):
        dish = self._dish("MON-DEF-A")
        dish._ensure_sale_product()
        kilo = self.env.ref("uom.product_uom_kgm")
        dish.serving_uom_id = kilo
        self.assertNotEqual(dish.product_id.uom_id, kilo)
        template = dish.product_id.product_tmpl_id
        order = self._order()
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.product_template_id = template
        line._onchange_product_template_id_set_menu_item()
        self.assertEqual(line.menu_item_id, dish)
        self.assertEqual(line.product_id, dish.product_id)
        self.assertEqual(line.price_unit, 45000.0)
        self.assertEqual(line.product_uom, kilo)

    def test_template_without_dish_syncs_list_price_and_uom(self):
        template = self._template("Thực phẩm rời", 30000.0)
        order = self._order("DH-DEF-002")
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.product_template_id = template
        line._onchange_product_template_id_set_menu_item()
        self.assertFalse(line.menu_item_id)
        self.assertEqual(line.product_id, template.product_variant_id)
        self.assertEqual(line.price_unit, 30000.0)
        self.assertEqual(line.product_uom, template.uom_id)

    def test_product_syncs_dish_price(self):
        dish = self._dish("MON-DEF-B")
        dish._ensure_sale_product()
        kilo = self.env.ref("uom.product_uom_kgm")
        dish.serving_uom_id = kilo
        order = self._order("DH-DEF-003")
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.product_id = dish.product_id
        line._onchange_product_id_set_menu_item()
        self.assertEqual(line.menu_item_id, dish)
        self.assertEqual(line.price_unit, 45000.0)
        self.assertEqual(line.product_uom, kilo)

    def test_create_defaults_template_price(self):
        template = self._template("Thực phẩm tạo", 25000.0)
        order = self._order("DH-DEF-004")
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 2.0,
            }
        )
        self.assertEqual(line.price_unit, 25000.0)

    def test_create_keeps_explicit_zero_price(self):
        template = self._template("Thực phẩm tặng", 25000.0)
        order = self._order("DH-DEF-005")
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 1.0,
                "price_unit": 0.0,
            }
        )
        self.assertEqual(line.price_unit, 0.0)

    def test_create_defaults_dish_price(self):
        dish = self._dish("MON-DEF-C", sale_price=55000.0)
        order = self._order("DH-DEF-006")
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "product_uom_qty": 2.0,
            }
        )
        self.assertEqual(line.price_unit, 55000.0)

    def test_qty_write_keeps_price(self):
        template = self._template("Thực phẩm giữ giá", 25000.0)
        order = self._order("DH-DEF-007")
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 1.0,
                "price_unit": 123000.0,
            }
        )
        line.write({"product_uom_qty": 9.0})
        self.assertEqual(line.price_unit, 123000.0)

    def test_price_and_uom_write_allowed(self):
        template = self._template("Thực phẩm sửa", 25000.0)
        order = self._order("DH-DEF-008")
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 1.0,
            }
        )
        kilo = self.env.ref("uom.product_uom_kgm")
        line.write({"price_unit": 999000.0, "product_uom": kilo.id})
        self.assertEqual(line.price_unit, 999000.0)
        self.assertEqual(line.product_uom, kilo)

    def test_tree_uom_column_after_qty(self):
        view = self.env.ref("set_top_menu.view_daily_order_form")
        tree = ET.fromstring(view.arch_db).find(
            ".//field[@name='order_line']/tree"
        )
        uoms = [
            field
            for field in tree.iter("field")
            if field.get("name") == "product_uom"
        ]
        self.assertEqual(len(uoms), 1)
        self.assertIsNone(uoms[0].get("column_invisible"))
        self.assertEqual(uoms[0].get("string"), "Đơn vị tính")
        names = [
            field.get("name") for field in tree if field.tag == "field"
        ]
        self.assertEqual(
            names.index("product_uom"), names.index("product_uom_qty") + 1
        )

    def test_form_qty_change_keeps_manual_price(self):
        template = self._template("Thực phẩm form", 30000.0)
        order = self._order("DH-DEF-009")
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.product_template_id = template
        line._onchange_product_template_id_set_menu_item()
        self.assertEqual(line.price_unit, 30000.0)
        line.price_unit = 99999.0
        line.product_uom_qty = 5.0
        self.assertEqual(line.price_unit, 99999.0)

    def test_dish_price_ignores_product_list_price(self):
        dish = self._dish("MON-DEF-D", sale_price=45000.0)
        dish._ensure_sale_product()
        dish.product_id.list_price = 0.0
        order = self._order("DH-DEF-010")
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.product_template_id = dish.product_id.product_tmpl_id
        line._onchange_product_template_id_set_menu_item()
        self.assertEqual(line.price_unit, 45000.0)

    def test_mismatched_uom_uses_list_price(self):
        template = self._template("Thực phẩm lệch ĐVT", 20000.0)
        kilo = self.env.ref("uom.product_uom_kgm")
        order = self._order("DH-DEF-011")
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.product_template_id = template
        line._onchange_product_template_id_set_menu_item()
        line.product_uom = kilo
        self.assertEqual(line.price_unit, 20000.0)

    def test_shared_picker_daily_form(self):
        view = self.env.ref("set_top_menu.view_daily_order_form")
        tree = ET.fromstring(view.arch_db).find(
            ".//field[@name='order_line']/tree"
        )
        picker = tree.find("./field[@name='product_template_id']")
        self.assertEqual(picker.get("string"), "Món ăn / Thực phẩm")
        names = [
            field.get("name") for field in tree if field.tag == "field"
        ]
        self.assertEqual(
            names.index("catering_line_type"),
            names.index("product_template_id") + 1,
        )
        badge = tree.find("./field[@name='catering_line_type']")
        self.assertEqual(badge.get("widget"), "badge")
        menu = tree.find("./field[@name='menu_item_id']")
        self.assertEqual(menu.get("column_invisible"), "True")

    def test_shared_picker_standard_form(self):
        form = self.env.ref("sale.view_order_form")
        tree = ET.fromstring(form.arch).find(
            ".//field[@name='order_line']/tree"
        )
        picker = tree.find("./field[@name='product_template_id']")
        self.assertEqual(picker.get("string"), "Món ăn / Thực phẩm")
        self.assertEqual(picker.get("domain"), "[]")
        names = [
            field.get("name") for field in tree if field.tag == "field"
        ]
        self.assertEqual(
            names.index("catering_line_type"),
            names.index("product_template_id") + 1,
        )
        menu = tree.find("./field[@name='menu_item_id']")
        self.assertEqual(menu.get("column_invisible"), "True")

    def test_line_type_compute(self):
        dish = self._dish("MON-DEF-G", sale_price=45000.0)
        dish._ensure_sale_product()
        template = self._template("Thực phẩm loại", 10000.0)
        order = self._order("DH-DEF-014")
        line = self.env["sale.order.line"].new({"order_id": order.id})
        self.assertFalse(line.catering_line_type)
        line.product_template_id = template
        line._onchange_product_template_id_set_menu_item()
        self.assertEqual(line.catering_line_type, "food")
        line.product_template_id = dish.product_id.product_tmpl_id
        line._onchange_product_template_id_set_menu_item()
        self.assertEqual(line.catering_line_type, "dish")

    def test_ensure_sale_product_heals_flags(self):
        dish = self._dish("MON-DEF-H", sale_price=45000.0)
        product = dish._ensure_sale_product()
        template = product.product_tmpl_id
        template.write({"sale_ok": False, "active": False})
        product.write({"active": False})
        dish._ensure_sale_product()
        self.assertTrue(template.sale_ok)
        self.assertTrue(template.active)
        self.assertTrue(product.sale_ok)
        self.assertTrue(product.active)
        dish.active = False
        template.write({"sale_ok": False, "active": False})
        product.write({"active": False})
        dish._ensure_sale_product()
        self.assertFalse(template.sale_ok)
        self.assertFalse(template.active)
        self.assertFalse(product.active)

    def test_picker_matches_material_list(self):
        field = self.env["sale.order.line"]._fields["product_template_id"]
        domain = literal_eval(field.domain)
        food = self.env["product.template"].create(
            {
                "name": "Thực phẩm bán được",
                "crall_food_source": "foods",
                "sale_ok": True,
            }
        )
        unsaleable = self.env["product.template"].create(
            {
                "name": "Thực phẩm không bán",
                "crall_food_source": "foods",
                "sale_ok": False,
            }
        )
        plain = self._template("Mẫu thường", 5000.0)
        dish = self._dish("MON-DEF-I", sale_price=45000.0)
        dish._ensure_sale_product()
        unsaleable_dish = self._dish("MON-DEF-J", sale_price=45000.0)
        unsaleable_dish_product = unsaleable_dish._ensure_sale_product()
        unsaleable_dish_product.write({"sale_ok": False})
        standard = self.env["product.template"].create(
            {"name": "Thực phẩm chuẩn", "crall_food_source": "standard"}
        )
        found = self.env["product.template"].search(domain)
        self.assertIn(food, found)
        self.assertIn(plain, found)
        self.assertIn(dish.product_id.product_tmpl_id, found)
        self.assertIn(unsaleable_dish_product.product_tmpl_id, found)
        self.assertNotIn(standard, found)
        self.assertNotIn(unsaleable, found)

    def test_dish_rename_syncs_sale_product(self):
        dish = self._dish("MON-DEF-L", sale_price=45000.0)
        product = dish._ensure_sale_product()
        dish.write({"name": "Món L tên mới", "item_code": "MON-DEF-L2"})
        self.assertEqual(product.name, "Món L tên mới")
        self.assertEqual(product.default_code, "MON-DEF-L2")

    def test_dish_write_heals_sale_product(self):
        dish = self._dish("MON-DEF-K", sale_price=45000.0)
        dish.product_id.unlink()
        self.assertFalse(dish.product_id)
        dish.write({"name": "Món K đã chữa"})
        self.assertTrue(dish.product_id)
        self.assertEqual(dish.product_id.name, "Món K đã chữa")
        self.assertTrue(dish.product_id.sale_ok)
        self.assertTrue(dish.product_id.active)
        self.assertTrue(dish.product_id.product_tmpl_id.sale_ok)
        self.assertTrue(dish.product_id.product_tmpl_id.active)

    def test_line_uom_dropdown_unfiltered(self):
        field = self.env["sale.order.line"]._fields["product_uom"]
        self.assertEqual(field.domain, "[]")

    def test_dish_uom_survives_recompute(self):
        dish = self._dish("MON-DEF-F", sale_price=45000.0)
        dish._ensure_sale_product()
        kilo = self.env.ref("uom.product_uom_kgm")
        dish.serving_uom_id = kilo
        order = self._order("DH-DEF-013")
        line = self.env["sale.order.line"].new({"order_id": order.id})
        line.menu_item_id = dish
        line.product_id = dish.product_id
        self.assertEqual(line.product_uom, kilo)

    def test_create_dish_line_uses_serving_uom(self):
        dish = self._dish("MON-DEF-E", sale_price=45000.0)
        kilo = self.env.ref("uom.product_uom_kgm")
        dish.serving_uom_id = kilo
        order = self._order("DH-DEF-012")
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "product_uom_qty": 1.0,
            }
        )
        self.assertEqual(line.product_uom, kilo)
        self.assertEqual(line.price_unit, 45000.0)

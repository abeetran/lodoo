import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOrderHnckPrices(TransactionCase):
    def _product(self, name, list_price):
        template = self.env["product.template"].create(
            {"name": name, "type": "product", "list_price": list_price}
        )
        return template.product_variant_id

    def _dish(self, code, sale_price):
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

    def _order(self, reference):
        partner = self.env["res.partner"].create(
            {"name": "Khách %s" % reference, "is_company": True}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
            }
        )

    def _dish_line(self, order, dish, quantity):
        meal = self.env.ref("set_top_menu.meal_type_lunch")
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "menu_item_id": dish.id,
                "meal_type_id": meal.id,
                "product_uom_qty": quantity,
            }
        )

    def _hnck_order(self, reference, state="draft"):
        order = self._order(reference)
        order.write({"hnck_order": True, "catering_state": state})
        return order

    def test_refresh_draft_updates_all_lines(self):
        food = self._product("Thực phẩm HNCK", 100.0)
        dish = self._dish("MON-HNCK-001", 50.0)
        order = self._order("DH-HNCK-001")
        food_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        dish_line = self._dish_line(order, dish, 3.0)
        order.write({"hnck_order": True})
        food_line.price_unit = 10.0
        dish_line.price_unit = 20.0
        food.product_tmpl_id.list_price = 150.0
        dish.sale_price = 60.0
        before = len(order.message_ids)
        result = order.action_update_hnck_prices()
        self.assertEqual(food_line.price_unit, 150.0)
        self.assertEqual(dish_line.price_unit, 60.0)
        self.assertEqual(order.catering_state, "draft")
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "success")
        self.assertEqual(len(order.message_ids), before + 1)

    def test_refresh_draft_without_lines_errors(self):
        order = self._hnck_order("DH-HNCK-001b")
        with self.assertRaises(UserError):
            order.action_update_hnck_prices()

    def test_refresh_delivered_updates_price_one_lines(self):
        food = self._product("Thực phẩm HNCK 1c", 100.0)
        order = self._order("DH-HNCK-001c")
        food_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        food_line.price_unit = 1.0
        order.write({"hnck_order": True, "catering_state": "delivered"})
        food.product_tmpl_id.list_price = 150.0
        result = order.action_update_hnck_prices()
        self.assertEqual(food_line.price_unit, 150.0)
        self.assertEqual(result["params"]["type"], "success")

    def test_refresh_non_draft_only_price_one_lines(self):
        food = self._product("Thực phẩm HNCK 2", 100.0)
        dish = self._dish("MON-HNCK-002", 50.0)
        order = self._order("DH-HNCK-002")
        food_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        dish_line = self._dish_line(order, dish, 3.0)
        food_line.price_unit = 1.0
        order.write({"hnck_order": True, "catering_state": "confirmed"})
        food.product_tmpl_id.list_price = 150.0
        dish.sale_price = 60.0
        result = order.action_update_hnck_prices()
        self.assertEqual(food_line.price_unit, 150.0)
        self.assertEqual(dish_line.price_unit, 50.0)
        self.assertEqual(result["params"]["type"], "success")

    def test_refresh_non_draft_without_placeholder_errors(self):
        food = self._product("Thực phẩm HNCK 3", 100.0)
        order = self._hnck_order("DH-HNCK-003", state="confirmed")
        self.env["sale.order.line"].with_context(hnck_sync=True).create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        with self.assertRaises(UserError):
            order.action_update_hnck_prices()

    def test_hnck_buttons_reject_system_orders(self):
        food = self._product("Thực phẩm hệ thống", 100.0)
        order = self._order("DH-SYS-001")
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        with self.assertRaises(UserError):
            order.action_update_hnck_prices()
        with self.assertRaises(UserError):
            order.action_enable_hnck_price_edit()

    def test_unlock_allows_only_price_unit(self):
        food = self._product("Thực phẩm HNCK 4", 100.0)
        order = self._hnck_order("DH-HNCK-004", state="confirmed")
        line = self.env["sale.order.line"].with_context(
            hnck_sync=True
        ).create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        with self.assertRaises(UserError):
            line.write({"price_unit": 120.0})
        self.assertFalse(order.hnck_price_editable)
        line.with_context(hnck_sync=True).write({"price_unit": 1.0})
        order.action_enable_hnck_price_edit()
        self.assertTrue(order.hnck_price_editable)
        line.write({"price_unit": 120.0})
        self.assertEqual(line.price_unit, 120.0)
        with self.assertRaises(UserError):
            line.write({"product_uom_qty": 5.0})
        with self.assertRaises(UserError):
            line.write({"catering_note": "ghi chú"})
        with self.assertRaises(UserError):
            order.write({"note": "ghi chú đơn"})

    def test_unlock_requires_placeholder_price(self):
        food = self._product("Thực phẩm HNCK 4b", 100.0)
        order = self._hnck_order("DH-HNCK-004b", state="confirmed")
        self.env["sale.order.line"].with_context(hnck_sync=True).create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        with self.assertRaises(UserError):
            order.action_enable_hnck_price_edit()
        self.assertFalse(order.hnck_price_editable)

    def test_unlock_is_idempotent_after_edit(self):
        food = self._product("Thực phẩm HNCK 4c", 100.0)
        order = self._hnck_order("DH-HNCK-004c", state="confirmed")
        line = self.env["sale.order.line"].with_context(
            hnck_sync=True
        ).create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        line.with_context(hnck_sync=True).write({"price_unit": 1.0})
        order.action_enable_hnck_price_edit()
        line.write({"price_unit": 120.0})
        self.assertEqual(line.price_unit, 120.0)
        self.assertTrue(order.action_enable_hnck_price_edit())
        self.assertTrue(order.hnck_price_editable)

    def test_unlock_keeps_draft_note_editable(self):
        food = self._product("Thực phẩm HNCK 5", 100.0)
        order = self._hnck_order("DH-HNCK-005")
        line = self.env["sale.order.line"].with_context(
            hnck_sync=True
        ).create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        line.with_context(hnck_sync=True).write({"price_unit": 1.0})
        order.action_enable_hnck_price_edit()
        line.write({"catering_note": "ghi chú draft"})
        self.assertEqual(line.catering_note, "ghi chú draft")

    def _unlocked_order(self, reference):
        food = self._product("Thực phẩm %s" % reference, 100.0)
        order = self._hnck_order(reference, state="confirmed")
        line = self.env["sale.order.line"].with_context(
            hnck_sync=True
        ).create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        line.with_context(hnck_sync=True).write({"price_unit": 1.0})
        order.action_enable_hnck_price_edit()
        return order, line

    def test_unlock_form_save_with_companions(self):
        order, line = self._unlocked_order("DH-HNCK-006")
        order.write(
            {
                "order_line": [
                    (
                        1,
                        line.id,
                        {
                            "price_unit": 120.0,
                            "product_id": line.product_id.id,
                            "menu_item_id": False,
                            "name": line.name,
                            "contract_task_id": False,
                        },
                    )
                ]
            }
        )
        self.assertEqual(line.price_unit, 120.0)
        self.assertEqual(line.product_uom_qty, 2.0)

    def test_unlock_form_save_blocks_changed_companion(self):
        order, line = self._unlocked_order("DH-HNCK-007")
        with self.assertRaises(UserError):
            order.write(
                {
                    "order_line": [
                        (
                            1,
                            line.id,
                            {
                                "price_unit": 120.0,
                                "product_uom_qty": 9.0,
                            },
                        )
                    ]
                }
            )

    def test_unlock_form_save_blocks_new_line(self):
        order, _line = self._unlocked_order("DH-HNCK-008")
        food = self._product("Thực phẩm thêm", 50.0)
        with self.assertRaises(UserError):
            order.write(
                {
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": food.id,
                                "product_uom_qty": 1.0,
                            },
                        )
                    ]
                }
            )

    def test_draft_form_save_price_with_companions(self):
        food = self._product("Thực phẩm HNCK 9", 100.0)
        order = self._hnck_order("DH-HNCK-009")
        line = self.env["sale.order.line"].with_context(
            hnck_sync=True
        ).create(
            {
                "order_id": order.id,
                "product_id": food.id,
                "product_uom_qty": 2.0,
            }
        )
        order.write(
            {
                "order_line": [
                    (
                        1,
                        line.id,
                        {
                            "price_unit": 130.0,
                            "catering_note": "ghi chú",
                            "product_id": food.id,
                            "name": line.name,
                        },
                    )
                ]
            }
        )
        self.assertEqual(line.price_unit, 130.0)
        self.assertEqual(line.catering_note, "ghi chú")

    def _daily_root(self):
        return ET.fromstring(
            self.env.ref("set_top_menu.view_daily_order_form").arch_db
        )

    def _sale_fragment(self):
        return ET.fromstring(
            self.env.ref("set_top_menu.view_order_form_menu_item").arch_db
        )

    def test_daily_form_hnck_buttons(self):
        root = self._daily_root()
        box = root.find(".//div[@name='button_box']")
        header = root.find(".//header")
        update = box.find(".//button[@name='action_update_hnck_prices']")
        edit = box.find(".//button[@name='action_enable_hnck_price_edit']")
        self.assertIsNotNone(update)
        self.assertIsNotNone(edit)
        self.assertIsNone(
            header.find(".//button[@name='action_update_hnck_prices']")
        )
        self.assertIsNone(
            header.find(".//button[@name='action_enable_hnck_price_edit']")
        )
        for node, hnck, flag, expected in (
            (update, True, False, True),
            (update, False, False, False),
            (edit, True, False, True),
            (edit, True, True, True),
            (edit, False, False, False),
        ):
            visible = not eval(
                node.get("invisible") or "False",
                {"__builtins__": {}},
                {"hnck_order": hnck, "hnck_price_editable": flag},
            )
            self.assertEqual(
                visible, expected, "%s hnck=%s flag=%s" % (node.get("name"), hnck, flag)
            )

    def test_daily_form_unlock_opens_only_price(self):
        root = self._daily_root()
        sheet = root.find(".//sheet")
        lines = root.find(".//field[@name='order_line']")
        for node, pick in ((sheet, 0), (lines, 1)):
            for hnck, state, flag, sheet_expected, lines_expected in (
                (True, "confirmed", False, True, True),
                (True, "confirmed", True, False, False),
                (False, "confirmed", False, False, False),
                (False, "ready", False, True, True),
                (True, "draft", False, True, False),
            ):
                readonly = eval(
                    node.get("readonly") or "False",
                    {"__builtins__": {}},
                    {
                        "hnck_order": hnck,
                        "catering_state": state,
                        "hnck_price_editable": flag,
                    },
                )
                expected = (sheet_expected, lines_expected)[pick]
                self.assertEqual(
                    bool(readonly),
                    expected,
                    "%s hnck=%s state=%s flag=%s"
                    % (node.tag, hnck, state, flag),
                )
        tree = lines.find("tree")
        delete = tree.find("control/delete")
        self.assertIsNotNone(delete)
        self.assertEqual(delete.get("invisible"), "parent.hnck_order")
        note = tree.find("field[@name='catering_note']")
        self.assertIn("hnck_price_editable", note.get("readonly"))
        price = tree.find("field[@name='price_unit']")
        self.assertEqual(price.get("readonly"), "parent.contract_id")
        for name in (
            "date_order",
            "partner_id",
            "contract_id",
            "catering_tax_id",
            "partner_shipping_id",
            "company_id",
            "note",
        ):
            node = root.find(".//field[@name='%s']" % name)
            self.assertIn(
                "hnck_price_editable",
                node.get("readonly") or "",
                name,
            )

    def test_sale_form_hnck_buttons(self):
        root = self._sale_fragment()
        boxes = [
            node
            for node in root.iter("xpath")
            if "button_box" in (node.get("expr") or "")
        ]
        self.assertTrue(boxes)
        update = edit = None
        for box in boxes:
            if update is None:
                update = box.find(
                    ".//button[@name='action_update_hnck_prices']"
                )
            if edit is None:
                edit = box.find(
                    ".//button[@name='action_enable_hnck_price_edit']"
                )
        helper = root.find(".//field[@name='hnck_price_editable']")
        self.assertIsNotNone(update)
        self.assertIsNotNone(edit)
        self.assertIsNotNone(helper)
        headers = [
            node
            for node in root.iter("xpath")
            if "header" in (node.get("expr") or "")
        ]
        for header in headers:
            self.assertIsNone(
                header.find(".//button[@name='action_update_hnck_prices']")
            )
            self.assertIsNone(
                header.find(
                    ".//button[@name='action_enable_hnck_price_edit']"
                )
            )
        self.assertEqual(update.get("invisible"), "not hnck_order")
        self.assertEqual(edit.get("invisible"), "not hnck_order")

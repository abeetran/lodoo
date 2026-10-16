import xml.etree.ElementTree as ET

from odoo.tests.common import TransactionCase


class TestPurchaseUomVisible(TransactionCase):
    def _buyer_arch(self):
        group = self.env.ref("purchase.group_purchase_user")
        user = self.env["res.users"].create(
            {
                "name": "Nhân viên mua ĐVT",
                "login": "buyer_uom_visible_test",
                "groups_id": [(6, 0, [group.id])],
            }
        )
        self.assertNotIn(
            self.env.ref("uom.group_uom"), user.groups_id
        )
        view = self.env.ref("purchase.purchase_order_form")
        arch = (
            self.env["purchase.order"]
            .with_user(user)
            .get_view(view_id=view.id, view_type="form")["arch"]
        )
        return ET.fromstring(arch)

    def test_uom_column_visible_on_lines_tree(self):
        root = self._buyer_arch()
        columns = root.findall(
            ".//field[@name='order_line']/tree/field[@name='product_uom']"
        )
        self.assertEqual(len(columns), 1)
        self.assertNotEqual(columns[0].get("column_invisible"), "True")
        self.assertEqual(columns[0].get("optional"), "show")
        self.assertEqual(columns[0].get("string"), "Đơn vị tính")

    def test_uom_visible_on_line_form(self):
        root = self._buyer_arch()
        order_line = root.find(".//field[@name='order_line']")
        form_uoms = [
            node
            for node in order_line.find("form").iter("field")
            if node.get("name") == "product_uom"
        ]
        self.assertEqual(len(form_uoms), 1)

    def test_uom_dropdown_has_no_category_domain(self):
        field = self.env["purchase.order.line"]._fields["product_uom"]
        self.assertEqual(field.domain, [])
        root = self._buyer_arch()
        columns = root.findall(
            ".//field[@name='order_line']/tree/field[@name='product_uom']"
        )
        self.assertEqual(len(columns), 1)
        self.assertIsNone(columns[0].get("domain"))

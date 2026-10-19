import xml.etree.ElementTree as ET

from odoo import fields
from odoo.tests.common import TransactionCase


class TestOrderSalesperson(TransactionCase):
    def test_daily_form_has_salesperson(self):
        view = self.env.ref("set_top_menu.view_daily_order_form")
        form = ET.fromstring(view.arch_db)
        nodes = {
            field.get("name"): field for field in form.iter("field")
        }
        self.assertIn("user_id", nodes)
        node = nodes["user_id"]
        self.assertEqual(node.get("string"), "Nhân viên kinh doanh")
        self.assertIn("share", node.get("domain"))
        self.assertNotEqual(node.get("invisible"), "1")

    def test_assigned_salesperson_counts_revenue(self):
        year = fields.Date.today().year
        seller = self.env["res.users"].create(
            {"name": "NVKD gán đơn", "login": "nvkd_assign_test"}
        )
        customer = self.env["res.partner"].create(
            {"name": "Khách NVKD-001", "is_company": True}
        )
        template = self.env["product.template"].create(
            {"name": "SP NVKD", "type": "product", "list_price": 100.0}
        )
        template.write({"taxes_id": [(5,)], "supplier_taxes_id": [(5,)]})
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "catering_reference": "DH-NVKD-001",
                "currency_id": self.env.ref("base.VND").id,
                "date_order": "%d-03-15 10:00:00" % year,
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 2.0,
            }
        )
        order.write({"user_id": seller.id, "catering_state": "delivered"})
        result = self.env["sale.order"].get_catering_dashboard_tops(
            "%d-01-01" % year, "%d-12-31" % year
        )
        users = {row["id"]: row for row in result["users"]}
        self.assertEqual(users[seller.id]["name"], seller.name)
        self.assertEqual(users[seller.id]["total"], 200.0)

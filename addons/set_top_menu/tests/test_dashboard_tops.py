from odoo import fields
from odoo.tests.common import TransactionCase


class TestDashboardTops(TransactionCase):
    def _partner(self, name):
        return self.env["res.partner"].create(
            {"name": name, "is_company": True}
        )

    def _product(self, name, list_price, food=False):
        template = self.env["product.template"].create(
            {"name": name, "type": "product", "list_price": list_price}
        )
        template.write({"taxes_id": [(5,)], "supplier_taxes_id": [(5,)]})
        if food:
            template.write({"crall_food_source": "foods"})
        return template.product_variant_id

    def _dish(self, product, code, name):
        return self.env["set_top_menu.menu.item"].create(
            {
                "name": name,
                "item_code": code,
                "serving_uom_id": product.uom_id.id,
                "product_id": product.id,
            }
        )

    def _sale_order(
        self, reference, partner, product, quantity, moment, user=None
    ):
        vnd = self.env.ref("base.VND")
        values = {
            "partner_id": partner.id,
            "catering_reference": reference,
            "currency_id": vnd.id,
            "date_order": moment,
        }
        if user is not None:
            values["user_id"] = user.id
        order = self.env["sale.order"].create(values)
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": quantity,
            }
        )
        return order

    def _purchase_order(self, partner, product, quantity, price, moment):
        vnd = self.env.ref("base.VND")
        order = self.env["purchase.order"].create(
            {
                "partner_id": partner.id,
                "currency_id": vnd.id,
                "date_order": moment,
            }
        )
        self.env["purchase.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_qty": quantity,
                "product_uom": product.uom_po_id.id,
                "price_unit": price,
            }
        )
        return order

    def test_tops_ranking_limit_and_product_amounts(self):
        year = fields.Date.today().year
        admin = self.env.ref("base.user_admin")
        seller = self.env["res.users"].create(
            {
                "name": "NV top",
                "login": "nv_top_test",
                "employee_code": "NV-TOP",
                "business_owner": True,
            }
        )
        big = self._partner("Khách TOP lớn")
        mid = self._partner("Khách TOP vừa")
        small = self._partner("Khách TOP nhỏ")
        product_a = self._product("SP top A", 100.0, food=True)
        product_b = self._product("SP top B", 50.0)
        self._dish(product_b, "MON-TOP-B", "Món top B")
        filler_product = self._product("SP top phụ", 10.0, food=True)
        plain_product = self._product("SP thường", 5.0)
        zero_product = self._product("SP 0 đồng", 0.0, food=True)
        vendor = self._partner("NCC TOP-001")
        first = self._sale_order(
            "DH-TOP-001", big, product_a, 5.0, "%d-03-15 10:00:00" % year
        )
        first.write({"user_id": seller.id, "catering_state": "delivered"})
        second = self._sale_order(
            "DH-TOP-002", mid, product_a, 2.0, "%d-03-16 10:00:00" % year
        )
        second.write({"catering_state": "delivered"})
        third = self._sale_order(
            "DH-TOP-003", small, product_b, 1.0, "%d-03-17 10:00:00" % year
        )
        third.write({"catering_state": "delivered"})
        skipped = self._sale_order(
            "DH-TOP-004", small, product_a, 9.0, "%d-03-18 10:00:00" % year
        )
        skipped.write({"catering_state": "cancelled"})
        plain = self._sale_order(
            "DH-TOP-005",
            self._partner("Khách TOP thường"),
            plain_product,
            1.0,
            "%d-03-18 10:00:00" % year,
        )
        plain.write({"user_id": seller.id, "catering_state": "delivered"})
        zero = self._sale_order(
            "DH-TOP-006",
            self._partner("Khách TOP 0 đồng"),
            zero_product,
            1.0,
            "%d-03-19 10:00:00" % year,
        )
        zero.write({"catering_state": "delivered"})
        for index in range(11):
            filler = self._sale_order(
                "DH-TOP-P-%02d" % index,
                self._partner("Khách TOP phụ %02d" % index),
                filler_product,
                1.0,
                "%d-03-10 10:00:00" % year,
            )
            filler.write({"catering_state": "delivered"})
        buy_a = self._purchase_order(
            vendor, product_a, 3.0, 60.0, "%d-03-11 10:00:00" % year
        )
        buy_a.button_confirm()
        buy_b = self._purchase_order(
            vendor, product_b, 2.0, 20.0, "%d-03-12 10:00:00" % year
        )
        buy_b.button_confirm()
        draft_buy = self._purchase_order(
            vendor, product_a, 1.0, 1000.0, "%d-03-13 10:00:00" % year
        )
        self.assertEqual(draft_buy.state, "draft")
        unsold = self._product("SP top không bán", 70.0)
        buy_unsold = self._purchase_order(
            vendor, unsold, 1.0, 70.0, "%d-03-14 10:00:00" % year
        )
        buy_unsold.button_confirm()
        result = self.env["sale.order"].get_catering_dashboard_tops(
            "%d-01-01" % year, "%d-12-31" % year
        )
        customers = result["customers"]
        self.assertEqual(len(customers), 10)
        self.assertEqual(customers[0]["id"], big.id)
        self.assertEqual(customers[0]["name"], big.display_name)
        self.assertEqual(customers[0]["total"], 500.0)
        self.assertEqual(
            [row["total"] for row in customers[:3]], [500.0, 200.0, 50.0]
        )
        users = {row["id"]: row for row in result["users"]}
        self.assertEqual(users[seller.id]["total"], 505.0)
        self.assertEqual(
            users[admin.id]["total"], 200.0 + 50.0 + 11 * 10.0
        )
        products = {row["id"]: row for row in result["products"]}
        self.assertEqual(
            set(products),
            {
                product_a.id,
                product_b.id,
                filler_product.id,
                plain_product.id,
            },
        )
        self.assertNotIn(zero_product.id, products)
        self.assertEqual(products[product_a.id]["sales"], 700.0)
        self.assertEqual(products[product_a.id]["purchase"], 180.0)
        self.assertEqual(products[product_a.id]["profit"], 520.0)
        self.assertEqual(products[product_b.id]["sales"], 50.0)
        self.assertEqual(products[product_b.id]["purchase"], 40.0)
        self.assertEqual(products[product_b.id]["profit"], 10.0)
        self.assertEqual(products[filler_product.id]["profit"], 110.0)
        self.assertEqual(products[plain_product.id]["sales"], 5.0)
        self.assertEqual(products[plain_product.id]["purchase"], 0.0)
        self.assertEqual(products[plain_product.id]["profit"], 5.0)
        self.assertEqual(
            [row["id"] for row in result["products"]],
            [product_a.id, filler_product.id, product_b.id, plain_product.id],
        )
        zero_only = self.env["sale.order"].get_catering_dashboard_tops(
            "%d-03-19" % year, "%d-03-19" % year
        )
        self.assertEqual(zero_only["customers"], [])
        self.assertEqual(zero_only["users"], [])
        self.assertEqual(zero_only["products"], [])

    def test_tops_filter_by_period_and_options(self):
        year = fields.Date.today().year
        customer_a = self._partner("Khách TOP-A")
        customer_b = self._partner("Khách TOP-B")
        vendor = self._partner("NCC TOP-002")
        product_a = self._product("SP top lọc A", 100.0, food=True)
        product_b = self._product("SP top lọc B", 100.0, food=True)
        march = self._sale_order(
            "DH-TOP-010",
            customer_a,
            product_a,
            1.0,
            "%d-03-15 10:00:00" % year,
        )
        march.write({"catering_state": "delivered"})
        january = self._sale_order(
            "DH-TOP-011",
            customer_b,
            product_b,
            1.0,
            "%d-01-15 10:00:00" % year,
        )
        january.write(
            {"hnck_order": True, "catering_state": "delivered"}
        )
        old_buy = self._purchase_order(
            vendor, product_a, 1.0, 60.0, "%d-01-12 10:00:00" % year
        )
        old_buy.button_confirm()
        march_buy = self._purchase_order(
            vendor, product_a, 1.0, 70.0, "%d-03-12 10:00:00" % year
        )
        march_buy.button_confirm()
        march_only = self.env[
            "sale.order"
        ].get_catering_dashboard_tops("%d-03-01" % year, "%d-03-31" % year)
        self.assertEqual(
            [row["id"] for row in march_only["customers"]], [customer_a.id]
        )
        self.assertEqual(len(march_only["products"]), 1)
        self.assertEqual(march_only["products"][0]["id"], product_a.id)
        self.assertEqual(march_only["products"][0]["sales"], 100.0)
        self.assertEqual(march_only["products"][0]["purchase"], 70.0)
        self.assertEqual(march_only["products"][0]["profit"], 30.0)
        full_year = self.env[
            "sale.order"
        ].get_catering_dashboard_tops("%d-01-01" % year, "%d-12-31" % year)
        self.assertEqual(len(full_year["customers"]), 2)
        only_hnck = self.env[
            "sale.order"
        ].get_catering_dashboard_tops(
            "%d-01-01" % year, "%d-12-31" % year, source="hnck"
        )
        self.assertEqual(
            [row["id"] for row in only_hnck["customers"]], [customer_b.id]
        )
        only_product = self.env[
            "sale.order"
        ].get_catering_dashboard_tops(
            "%d-01-01" % year, "%d-12-31" % year, product_id=product_b.id
        )
        self.assertEqual(
            [row["id"] for row in only_product["customers"]], [customer_b.id]
        )
        self.assertEqual(
            [row["id"] for row in only_product["products"]], [product_b.id]
        )

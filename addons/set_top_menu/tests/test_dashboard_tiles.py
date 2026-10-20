from datetime import datetime

from odoo import fields
from odoo.tests.common import TransactionCase


class TestDashboardTiles(TransactionCase):
    def _partner(self, name):
        return self.env["res.partner"].create(
            {"name": name, "is_company": True}
        )

    def _product(self, name, list_price, quantity=0.0):
        template = self.env["product.template"].create(
            {"name": name, "type": "product", "list_price": list_price}
        )
        product = template.product_variant_id
        if quantity:
            location = self.env.ref("stock.stock_location_stock")
            self.env["stock.quant"]._update_available_quantity(
                product, location, quantity
            )
        return product

    def _order(self, reference, partner, product, quantity, **extra):
        extra.setdefault("currency_id", self.env.ref("base.VND").id)
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
                **extra,
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": quantity,
            }
        )
        return order

    def _empty_outgoing(self):
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "outgoing")], limit=1
        )
        self.assertTrue(picking_type, "Thiếu loại lệnh outgoing")
        return self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "user_id": self.env.ref("base.user_admin").id,
                "location_id": self.env.ref("stock.stock_location_stock").id,
                "location_dest_id": self.env.ref(
                    "stock.stock_location_customers"
                ).id,
            }
        )

    def _delivering_picking(self, order, scheduled_date=False):
        picking = self._empty_outgoing()
        picking.write(
            {
                "partner_id": order.partner_id.id,
                "sale_order_id": order.id,
            }
        )
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        picking.button_validate()
        self.assertEqual(picking.state, "delivering")
        if scheduled_date:
            picking.write({"scheduled_date": scheduled_date})
        return picking

    def _period(self):
        today = fields.Date.today()
        return (
            fields.Date.to_string(today.replace(day=1)),
            fields.Date.to_string(today),
        )

    def test_tiles_count_period_and_amounts(self):
        today = fields.Date.today()
        in_period = fields.Datetime.to_string(today)
        out_period = fields.Datetime.to_string(
            today.replace(year=today.year - 1)
        )
        partner = self._partner("Khách TILE-001")
        product = self._product("SP tile", 100.0, quantity=20.0)
        cancelled = self._order(
            "DH-TILE-001", partner, product, 1.0, date_order=in_period
        )
        cancelled.write({"catering_state": "cancelled"})
        old_cancelled = self._order(
            "DH-TILE-002", partner, product, 1.0, date_order=out_period
        )
        old_cancelled.write({"catering_state": "cancelled"})
        returned = self._order(
            "DH-TILE-003", partner, product, 1.0, date_order=in_period
        )
        returned.write({"catering_state": "returned"})
        delivered = self._order(
            "DH-TILE-004", partner, product, 2.0, date_order=in_period
        )
        delivered.write({"catering_state": "delivered"})
        old_delivered = self._order(
            "DH-TILE-005", partner, product, 5.0, date_order=out_period
        )
        old_delivered.write({"catering_state": "delivered"})
        linked = self._order(
            "DH-TILE-006", partner, product, 3.0, date_order=in_period
        )
        self._delivering_picking(linked)
        old_linked = self._order(
            "DH-TILE-007", partner, product, 9.0, date_order=in_period
        )
        old_picking = self._delivering_picking(old_linked)
        old_picking.write({"scheduled_date": out_period})
        date_from, date_to = self._period()
        result = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to
        )
        self.assertEqual(result["date_from"], date_from)
        self.assertEqual(result["date_to"], date_to)
        vnd = self.env.ref("base.VND")
        self.assertEqual(result["currency_symbol"], vnd.symbol)
        self.assertEqual(result["currency_position"], vnd.position)
        self.assertEqual(result["cancelled_count"], 1)
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["delivering_count"], 1)
        self.assertEqual(result["delivering_amount"], 300.0)
        self.assertEqual(result["delivered_count"], 1)
        self.assertEqual(result["delivered_amount"], 200.0)

    def test_filter_options_lists(self):
        partner = self._partner("Khách OPT-001")
        product = self._product("SP opt", 100.0)
        team = self.env["crm.team"].create({"name": "Team OPT"})
        admin = self.env.ref("base.user_admin")
        buyer = self._order("DH-OPT-001", partner, product, 1.0)
        buyer.action_confirm()
        options = self.env["sale.order"].get_catering_dashboard_filters()
        self.assertIn(
            product.id, [item["id"] for item in options["products"]]
        )
        self.assertIn(
            partner.id, [item["id"] for item in options["partners"]]
        )
        self.assertIn(team.id, [item["id"] for item in options["teams"]])
        self.assertIn(admin.id, [item["id"] for item in options["users"]])
        labels = {item["id"]: item["label"] for item in options["products"]}
        self.assertIn(product.display_name, labels[product.id])

    def test_tiles_filter_by_product(self):
        date_from, date_to = self._period()
        partner = self._partner("Khách FLT-001")
        product_a = self._product("SP lọc A", 100.0, quantity=20.0)
        product_b = self._product("SP lọc B", 50.0)
        order_a = self._order("DH-FLT-001", partner, product_a, 2.0)
        order_a.write({"catering_state": "delivered"})
        order_b = self._order("DH-FLT-002", partner, product_b, 1.0)
        order_b.write({"catering_state": "delivered"})
        linked = self._order("DH-FLT-003", partner, product_a, 1.0)
        self._delivering_picking(linked)
        only_a = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, product_id=product_a.id
        )
        self.assertEqual(only_a["delivered_count"], 1)
        self.assertEqual(only_a["delivered_amount"], 200.0)
        self.assertEqual(only_a["delivering_count"], 1)
        self.assertEqual(only_a["delivering_amount"], 100.0)
        only_b = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, product_id=product_b.id
        )
        self.assertEqual(only_b["delivered_count"], 1)
        self.assertEqual(only_b["delivered_amount"], 50.0)
        self.assertEqual(only_b["delivering_count"], 0)
        self.assertEqual(only_b["delivering_amount"], 0.0)

    def test_tiles_filter_by_partner(self):
        date_from, date_to = self._period()
        partner_a = self._partner("Khách FLT-A")
        partner_b = self._partner("Khách FLT-B")
        product = self._product("SP lọc KH", 100.0, quantity=20.0)
        order_a = self._order("DH-FLT-010", partner_a, product, 2.0)
        order_a.write({"catering_state": "delivered"})
        order_b = self._order("DH-FLT-011", partner_b, product, 1.0)
        order_b.write({"catering_state": "delivered"})
        linked = self._order("DH-FLT-012", partner_a, product, 1.0)
        picking = self._delivering_picking(linked)
        picking.write({"partner_id": partner_b.id})
        only_a = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, partner_id=partner_a.id
        )
        self.assertEqual(only_a["delivered_count"], 1)
        self.assertEqual(only_a["delivered_amount"], 200.0)
        self.assertEqual(only_a["delivering_count"], 1)
        only_b = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, partner_id=partner_b.id
        )
        self.assertEqual(only_b["delivered_count"], 1)
        self.assertEqual(only_b["delivering_count"], 1)

    def test_tiles_filter_by_team_user_source(self):
        date_from, date_to = self._period()
        partner = self._partner("Khách FLT-T")
        product = self._product("SP lọc team", 100.0, quantity=20.0)
        team_a = self.env["crm.team"].create({"name": "Team A"})
        team_b = self.env["crm.team"].create({"name": "Team B"})
        admin = self.env.ref("base.user_admin")
        seller = self.env["res.users"].create(
            {
                "name": "NV bán hàng",
                "login": "nv_tile_test",
                "employee_code": "NV-TILE",
                "business_owner": True,
            }
        )
        order_a = self._order(
            "DH-FLT-020",
            partner,
            product,
            1.0,
            team_id=team_a.id,
            user_id=admin.id,
        )
        order_a.write({"catering_state": "delivered"})
        order_b = self._order(
            "DH-FLT-021",
            partner,
            product,
            1.0,
            team_id=team_b.id,
            user_id=admin.id,
        )
        order_b.write({"catering_state": "delivered"})
        order_c = self._order(
            "DH-FLT-022",
            partner,
            product,
            1.0,
            team_id=team_a.id,
            user_id=seller.id,
        )
        order_c.write({"catering_state": "delivered"})
        order_d = self._order(
            "DH-FLT-023",
            partner,
            product,
            1.0,
            team_id=team_a.id,
            user_id=admin.id,
        )
        order_d.write({"hnck_order": True, "catering_state": "delivered"})
        self._delivering_picking(order_a)
        only_team_a = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, team_id=team_a.id
        )
        self.assertEqual(only_team_a["delivered_count"], 3)
        self.assertEqual(only_team_a["delivering_count"], 1)
        only_team_b = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, team_id=team_b.id
        )
        self.assertEqual(only_team_b["delivered_count"], 1)
        self.assertEqual(only_team_b["delivering_count"], 0)
        only_seller = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, user_id=seller.id
        )
        self.assertEqual(only_seller["delivered_count"], 1)
        self.assertEqual(only_seller["delivering_count"], 0)
        only_hnck = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, source="hnck"
        )
        self.assertEqual(only_hnck["delivered_count"], 1)
        self.assertEqual(only_hnck["delivering_count"], 0)
        only_internal = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, source="internal"
        )
        self.assertEqual(only_internal["delivered_count"], 3)
        self.assertEqual(only_internal["delivering_count"], 1)
        combined = self.env["sale.order"].get_catering_dashboard_tiles(
            date_from, date_to, team_id=team_a.id, source="hnck"
        )
        self.assertEqual(combined["delivered_count"], 1)
        self.assertEqual(combined["delivering_count"], 0)
        unknown_source = self.env[
            "sale.order"
        ].get_catering_dashboard_tiles(date_from, date_to, source="xxx")
        self.assertEqual(unknown_source["delivered_count"], 4)
        self.assertEqual(unknown_source["delivering_count"], 1)

    def test_sales_chart_monthly_totals(self):
        year = fields.Date.today().year

        def at(month, day, for_year=None):
            return fields.Datetime.to_string(
                datetime(for_year or year, month, day)
            )

        partner = self._partner("Khách CHT-001")
        product = self._product("SP biểu đồ", 100.0)
        for reference, moment, quantity, state in (
            ("DH-CHT-001", at(1, 15), 2.0, "delivered"),
            ("DH-CHT-002", at(1, 20), 1.0, "delivered"),
            ("DH-CHT-003", at(3, 10), 1.0, "delivered"),
            ("DH-CHT-004", at(3, 11), 1.0, "cancelled"),
            ("DH-CHT-005", at(6, 10, year - 1), 1.0, "delivered"),
        ):
            order = self._order(
                reference, partner, product, quantity, date_order=moment
            )
            order.write({"catering_state": state})
        today = fields.Date.to_string(fields.Date.today())
        result = self.env["sale.order"].get_catering_dashboard_sales_chart(
            today, today
        )
        by_key = {month["key"]: month["total"] for month in result["months"]}
        self.assertEqual(len(result["months"]), 12)
        self.assertEqual(by_key["%d-01" % year], 300.0)
        self.assertEqual(by_key["%d-03" % year], 100.0)
        self.assertEqual(sum(by_key.values()), 400.0)
        labels = {month["key"]: month["label"] for month in result["months"]}
        self.assertEqual(labels["%d-01" % year], "01/%d" % year)

    def test_sales_chart_respects_filters(self):
        date_from, date_to = self._period()
        partner_a = self._partner("Khách CHT-A")
        partner_b = self._partner("Khách CHT-B")
        product_a = self._product("SP CHT A", 100.0)
        product_b = self._product("SP CHT B", 100.0)
        first = self._order("DH-CHT-010", partner_a, product_a, 1.0)
        first.write({"catering_state": "delivered"})
        second = self._order("DH-CHT-011", partner_b, product_b, 1.0)
        second.write({"catering_state": "delivered"})
        third = self._order("DH-CHT-012", partner_a, product_a, 1.0)
        third.write({"hnck_order": True, "catering_state": "delivered"})

        def total(**kwargs):
            result = self.env[
                "sale.order"
            ].get_catering_dashboard_sales_chart(
                date_from, date_to, **kwargs
            )
            return sum(month["total"] for month in result["months"])

        self.assertEqual(total(product_id=product_a.id), 200.0)
        self.assertEqual(total(product_id=product_b.id), 100.0)
        self.assertEqual(total(partner_id=partner_b.id), 100.0)
        self.assertEqual(total(source="hnck"), 100.0)
        self.assertEqual(total(source="internal"), 200.0)
        self.assertEqual(
            total(product_id=product_a.id, source="hnck"), 100.0
        )

    def test_sales_chart_no_orders_returns_zeros(self):
        year = fields.Date.today().year
        result = self.env["sale.order"].get_catering_dashboard_sales_chart(
            "2020-01-01", "2020-01-31"
        )
        self.assertEqual(len(result["months"]), 12)
        self.assertEqual(result["months"][0]["key"], "%d-01" % year)
        self.assertEqual(result["months"][0]["label"], "01/%d" % year)
        for month in result["months"]:
            self.assertEqual(month["total"], 0.0)

    def test_tiles_default_to_current_month(self):
        date_from, date_to = self._period()
        result = self.env["sale.order"].get_catering_dashboard_tiles()
        self.assertEqual(result["date_from"], date_from)
        self.assertEqual(result["date_to"], date_to)

    def test_tiles_invalid_and_swapped_dates(self):
        date_from, date_to = self._period()
        result = self.env["sale.order"].get_catering_dashboard_tiles(
            "not-a-date", False
        )
        self.assertEqual(result["date_from"], date_from)
        self.assertEqual(result["date_to"], date_to)
        swapped = self.env["sale.order"].get_catering_dashboard_tiles(
            date_to, date_from
        )
        self.assertEqual(swapped["date_from"], date_from)
        self.assertEqual(swapped["date_to"], date_to)

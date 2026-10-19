from odoo import fields
from odoo.tests.common import TransactionCase


class TestDashboardStatistics(TransactionCase):
    def _partner(self, name):
        return self.env["res.partner"].create(
            {"name": name, "is_company": True}
        )

    def _product(self, name, list_price):
        template = self.env["product.template"].create(
            {"name": name, "type": "product", "list_price": list_price}
        )
        template.write({"taxes_id": [(5,)], "supplier_taxes_id": [(5,)]})
        return template.product_variant_id

    def _sale_order(self, reference, partner, product, quantity, moment):
        vnd = self.env.ref("base.VND")
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "catering_reference": reference,
                "currency_id": vnd.id,
                "date_order": moment,
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

    def _purchase_order(
        self, partner, product, quantity, price, moment, currency=None
    ):
        vnd = self.env.ref("base.VND")
        order = self.env["purchase.order"].create(
            {
                "partner_id": partner.id,
                "currency_id": (currency or vnd).id,
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

    def test_statistics_totals_and_months(self):
        year = fields.Date.today().year
        customer = self._partner("Khách STT-001")
        vendor = self._partner("NCC STT-001")
        product = self._product("SP thống kê", 100.0)
        first = self._sale_order(
            "DH-STT-001", customer, product, 2.0, "%d-01-15 10:00:00" % year
        )
        first.write({"catering_state": "delivered"})
        second = self._sale_order(
            "DH-STT-002", customer, product, 1.0, "%d-03-20 10:00:00" % year
        )
        second.write({"catering_state": "delivered"})
        skipped = self._sale_order(
            "DH-STT-003", customer, product, 1.0, "%d-03-21 10:00:00" % year
        )
        skipped.write({"catering_state": "cancelled"})
        old = self._sale_order(
            "DH-STT-004",
            customer,
            product,
            1.0,
            "%d-06-10 10:00:00" % (year - 1),
        )
        old.write({"catering_state": "delivered"})
        confirmed = self._purchase_order(
            vendor, product, 1.0, 50.0, "%d-01-12 10:00:00" % year
        )
        confirmed.button_confirm()
        other = self._purchase_order(
            vendor, product, 1.0, 30.0, "%d-03-11 10:00:00" % year
        )
        other.button_confirm()
        draft = self._purchase_order(
            vendor, product, 1.0, 1000.0, "%d-02-10 10:00:00" % year
        )
        self.assertEqual(draft.state, "draft")
        cancelled = self._purchase_order(
            vendor, product, 1.0, 500.0, "%d-02-11 10:00:00" % year
        )
        cancelled.button_cancel()
        last_year = self._purchase_order(
            vendor,
            product,
            1.0,
            400.0,
            "%d-04-10 10:00:00" % (year - 1),
        )
        last_year.button_confirm()
        result = self.env["sale.order"].get_catering_dashboard_statistics()
        self.assertEqual(result["year"], year)
        self.assertEqual(result["revenue"], 300.0)
        self.assertEqual(result["purchase"], 80.0)
        self.assertEqual(result["profit"], 220.0)
        self.assertEqual(len(result["months"]), 12)
        by_key = {month["key"]: month for month in result["months"]}
        january = by_key["%d-01" % year]
        self.assertEqual(january["label"], "01/%d" % year)
        self.assertEqual(january["revenue"], 200.0)
        self.assertEqual(january["purchase"], 50.0)
        self.assertEqual(january["profit"], 150.0)
        march = by_key["%d-03" % year]
        self.assertEqual(march["revenue"], 100.0)
        self.assertEqual(march["purchase"], 30.0)
        self.assertEqual(march["profit"], 70.0)
        june = by_key["%d-06" % year]
        self.assertEqual(june["revenue"], 0.0)
        self.assertEqual(june["purchase"], 0.0)
        self.assertEqual(june["profit"], 0.0)

    def test_statistics_filters_by_query_period(self):
        year = fields.Date.today().year
        customer = self._partner("Khách STT-010")
        vendor = self._partner("NCC STT-010")
        product = self._product("SP lọc kỳ", 100.0)
        january = self._sale_order(
            "DH-STT-010", customer, product, 2.0, "%d-01-15 10:00:00" % year
        )
        january.write({"catering_state": "delivered"})
        march = self._sale_order(
            "DH-STT-011", customer, product, 1.0, "%d-03-20 10:00:00" % year
        )
        march.write({"catering_state": "delivered"})
        first_buy = self._purchase_order(
            vendor, product, 1.0, 50.0, "%d-01-12 10:00:00" % year
        )
        first_buy.button_confirm()
        second_buy = self._purchase_order(
            vendor, product, 1.0, 30.0, "%d-03-11 10:00:00" % year
        )
        second_buy.button_confirm()
        result = self.env["sale.order"].get_catering_dashboard_statistics(
            "%d-03-01" % year, "%d-03-31" % year
        )
        self.assertEqual(result["year"], year)
        self.assertEqual(result["date_from"], "%d-03-01" % year)
        self.assertEqual(result["date_to"], "%d-03-31" % year)
        self.assertEqual(
            result["period_label"],
            "từ 01/03/%d đến 31/03/%d" % (year, year),
        )
        self.assertEqual(result["revenue"], 100.0)
        self.assertEqual(result["purchase"], 30.0)
        self.assertEqual(result["profit"], 70.0)
        self.assertEqual(len(result["months"]), 1)
        month = result["months"][0]
        self.assertEqual(month["key"], "%d-03" % year)
        self.assertEqual(month["label"], "03/%d" % year)
        self.assertEqual(month["revenue"], 100.0)
        self.assertEqual(month["purchase"], 30.0)
        self.assertEqual(month["profit"], 70.0)

    def test_statistics_swapped_and_cross_year_period(self):
        year = fields.Date.today().year
        customer = self._partner("Khách STT-011")
        product = self._product("SP lọc năm", 100.0)
        december = self._sale_order(
            "DH-STT-012",
            customer,
            product,
            1.5,
            "%d-12-20 10:00:00" % (year - 1),
        )
        december.write({"catering_state": "delivered"})
        january = self._sale_order(
            "DH-STT-013", customer, product, 2.0, "%d-01-10 10:00:00" % year
        )
        january.write({"catering_state": "delivered"})
        february = self._sale_order(
            "DH-STT-014", customer, product, 5.0, "%d-02-10 10:00:00" % year
        )
        february.write({"catering_state": "delivered"})
        result = self.env["sale.order"].get_catering_dashboard_statistics(
            "%d-01-31" % year, "%d-12-01" % (year - 1)
        )
        self.assertEqual(result["date_from"], "%d-12-01" % (year - 1))
        self.assertEqual(result["date_to"], "%d-01-31" % year)
        self.assertEqual(result["revenue"], 350.0)
        self.assertEqual(
            [month["key"] for month in result["months"]],
            ["%d-12" % (year - 1), "%d-01" % year],
        )
        by_key = {month["key"]: month for month in result["months"]}
        self.assertEqual(
            by_key["%d-12" % (year - 1)]["revenue"], 150.0
        )
        self.assertEqual(by_key["%d-01" % year]["revenue"], 200.0)

    def test_statistics_full_year_range_keeps_year_label(self):
        year = fields.Date.today().year
        result = self.env["sale.order"].get_catering_dashboard_statistics(
            "%d-01-01" % year, "%d-12-31" % year
        )
        self.assertEqual(result["year"], year)
        self.assertEqual(result["period_label"], "năm %d" % year)
        self.assertEqual(len(result["months"]), 12)
        self.assertEqual(result["months"][0]["key"], "%d-01" % year)
        self.assertEqual(result["months"][-1]["key"], "%d-12" % year)

    def test_statistics_converts_purchase_to_vnd(self):
        vendor = self._partner("NCC STT-002")
        product = self._product("SP ngoại tệ mua", 100.0)
        company = self.env.company
        vnd = self.env.ref("base.VND")
        usd = self.env.ref("base.USD")
        for currency, rate in ((usd, 1.0), (vnd, 25000.0)):
            self.env["res.currency.rate"].create(
                {
                    "name": "2020-01-01",
                    "rate": rate,
                    "currency_id": currency.id,
                    "company_id": company.id,
                }
            )
        order = self._purchase_order(
            vendor,
            product,
            1.0,
            100.0,
            fields.Datetime.now(),
            currency=usd,
        )
        order.button_confirm()
        result = self.env["sale.order"].get_catering_dashboard_statistics()
        expected = usd._convert(
            100.0, vnd, company, order.date_order
        )
        self.assertEqual(result["revenue"], 0.0)
        self.assertEqual(result["purchase"], expected)
        self.assertNotEqual(result["purchase"], 100.0)
        self.assertEqual(result["profit"], -expected)

/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Dashboard bán hàng: 4 ô Đơn hủy / Đơn trả / Đang giao / Đã giao
 * theo kỳ ngày và các điều kiện lọc (mặc định tháng hiện tại).
 */
export class CateringDashboard extends Component {
    static template = "set_top_menu.CateringDashboard";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            dateFrom: "",
            dateTo: "",
            productInput: "",
            partnerInput: "",
            teamId: "",
            userId: "",
            source: "",
            products: [],
            partners: [],
            teams: [],
            users: [],
            chartMonths: [],
            statsYear: "",
            revenueTotal: 0,
            purchaseTotal: 0,
            profitTotal: 0,
            profitMonths: [],
            currencySymbol: "",
            currencyPosition: "after",
            cancelledCount: 0,
            returnedCount: 0,
            deliveringCount: 0,
            deliveringAmount: 0,
            deliveredCount: 0,
            deliveredAmount: 0,
        });
        onWillStart(async () => {
            await this.loadFilters();
            await this.loadTiles();
        });
    }

    async loadFilters() {
        const filters = await this.orm.call(
            "sale.order",
            "get_catering_dashboard_filters",
            []
        );
        Object.assign(this.state, {
            products: filters.products,
            partners: filters.partners,
            teams: filters.teams,
            users: filters.users,
        });
    }

    selectedId(options, input) {
        const found = options.find((option) => option.label === input);
        return found ? found.id : false;
    }

    filterArgs() {
        return [
            this.state.dateFrom || false,
            this.state.dateTo || false,
            this.selectedId(this.state.products, this.state.productInput),
            this.selectedId(this.state.partners, this.state.partnerInput),
            Number(this.state.teamId) || false,
            Number(this.state.userId) || false,
            this.state.source || false,
        ];
    }

    get chartTop() {
        const totals = this.state.chartMonths.map((month) => month.total);
        const step = Math.max(1, Math.ceil(Math.max(0, ...totals) / 4));
        return step * 4;
    }

    get yTicks() {
        const top = this.chartTop;
        const step = top / 4;
        return [top, top - step, top - step * 2, top - step * 3, 0];
    }

    barHeight(total) {
        if (!total || !this.chartTop) {
            return 0;
        }
        return Math.max(3, Math.round((total / this.chartTop) * 160));
    }

    get profitTop() {
        const values = this.state.profitMonths.map((month) =>
            Math.abs(month.profit)
        );
        const step = Math.max(1, Math.ceil(Math.max(0, ...values) / 4));
        return step * 4;
    }

    get profitTicks() {
        const top = this.profitTop;
        const step = top / 4;
        return [top, top - step, top - step * 2, top - step * 3, 0];
    }

    profitBarHeight(profit) {
        if (!profit || !this.profitTop) {
            return 0;
        }
        return Math.max(
            3,
            Math.round((Math.abs(profit) / this.profitTop) * 160)
        );
    }

    formatCompact(value) {
        const abs = Math.abs(value || 0);
        const trimmed = (number, digits) =>
            number.toLocaleString("vi-VN", { maximumFractionDigits: digits });
        if (abs >= 1e9) {
            return `${trimmed(value / 1e9, 2)} tỷ`;
        }
        if (abs >= 1e6) {
            return `${trimmed(value / 1e6, 2)} Tr`;
        }
        return trimmed(value || 0, 0);
    }

    async loadTiles() {
        const args = this.filterArgs();
        const [data, chart, stats] = await Promise.all([
            this.orm.call("sale.order", "get_catering_dashboard_tiles", args),
            this.orm.call(
                "sale.order",
                "get_catering_dashboard_sales_chart",
                args
            ),
            this.orm.call(
                "sale.order",
                "get_catering_dashboard_statistics",
                []
            ),
        ]);
        Object.assign(this.state, {
            dateFrom: data.date_from,
            dateTo: data.date_to,
            chartMonths: chart.months,
            statsYear: stats.year,
            revenueTotal: stats.revenue,
            purchaseTotal: stats.purchase,
            profitTotal: stats.profit,
            profitMonths: stats.months,
            currencySymbol: data.currency_symbol,
            currencyPosition: data.currency_position,
            cancelledCount: data.cancelled_count,
            returnedCount: data.returned_count,
            deliveringCount: data.delivering_count,
            deliveringAmount: data.delivering_amount,
            deliveredCount: data.delivered_count,
            deliveredAmount: data.delivered_amount,
        });
    }

    async clearFilters() {
        Object.assign(this.state, {
            productInput: "",
            partnerInput: "",
            teamId: "",
            userId: "",
            source: "",
        });
        await this.loadTiles();
    }

    formatAmount(value) {
        const formatted = Number(value || 0).toLocaleString("vi-VN", {
            maximumFractionDigits: 0,
        });
        if (this.state.currencyPosition === "before") {
            return `${this.state.currencySymbol} ${formatted}`;
        }
        return `${formatted} ${this.state.currencySymbol}`;
    }
}

registry
    .category("actions")
    .add("set_top_menu.catering_dashboard", CateringDashboard);

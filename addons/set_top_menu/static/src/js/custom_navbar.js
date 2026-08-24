/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);

        // Odoo action service
        this.actionService = useService("action");

        // Custom top navigation items
        this.customNavItems = [
            {
                id: "dashboard",
                label: "Bảng điều khiển",
                icon: "fa-tachometer",
                url: "/web#dashboard_id=8&cids=1&menu_id=173&action=294",
            },
            {
                id: "clients",
                label: "Khách hàng",
                icon: "fa-users",
                action: "set_top_menu.action_client_management",
                children: [
                    {
                        id: "contracts",
                        label: "Hợp đồng",
                        icon: "fa-file-text-o",
                        action: "set_top_menu.action_client_contracts",
                    },
                ],
            },
            {
                id: "menus",
                label: "Thực đơn",
                icon: "fa-list",
                action: "set_top_menu.action_menu_items",
            },
            {
                id: "orders",
                label: "Đơn hàng",
                icon: "fa-shopping-cart",
                action: "set_top_menu.action_daily_orders",
            },
            {
                id: "kitchen",
                label: "Bếp",
                icon: "fa-cutlery",
                action: "set_top_menu.action_kitchen_plans",
            },
            {
                id: "billing",
                label: "Hóa đơn",
                icon: "fa-file-text-o",
                action: "account.action_move_out_invoice_type",
            },
            {
                id: "materials",
                label: "Nguyên liệu",
                icon: "fa-cubes",
                action: "set_top_menu.action_material_products",
            },
            {
                id: "delivery",
                label: "Giao hàng",
                icon: "fa-truck",
                action: "stock.action_picking_tree_all",
            },
            // {
            //     id: "client_relations",
            //     label: "Client Relations",
            //     icon: "fa-handshake-o",
            //     action: "crm.crm_lead_action_pipeline",
            // },
            {
                id: "configuration",
                label: "Cấu hình",
                icon: "fa-cog",
                action: "base.action_res_users",
            },
        ];
    },

    /**
     * Handle custom navbar item click
     */
    async onCustomNavClick(item) {
        if (!item) {
            return;
        }

        if (item.url) {
            window.location.assign(item.url);
            return;
        }

        if (!item.action) {
            return;
        }

        if (!this.actionService) {
            console.error("Action service is not available.");
            return;
        }

        try {
            await this.actionService.doAction(item.action);
        } catch (error) {
            console.error(
                "Cannot execute action:",
                item.action,
                error
            );
        }
    },
});

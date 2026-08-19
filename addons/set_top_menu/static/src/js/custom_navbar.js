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
                label: "Dashboard",
                icon: "fa-tachometer",
                action: "base.open_menu",
            },
            {
                id: "clients",
                label: "Clients",
                icon: "fa-users",
                action: "set_top_menu.action_client_management",
                children: [
                    {
                        id: "contracts",
                        label: "Contracts",
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
                label: "Orders",
                icon: "fa-shopping-cart",
                action: "sale.action_orders",
            },
            {
                id: "kitchen",
                label: "Kitchen",
                icon: "fa-cutlery",
                action: null,
            },
            {
                id: "billing",
                label: "Billing",
                icon: "fa-file-text-o",
                action: "account.action_move_out_invoice_type",
            },
            {
                id: "materials",
                label: "Materials",
                icon: "fa-cubes",
                action: "stock.action_product_production_lot_form",
            },
            {
                id: "delivery",
                label: "Delivery",
                icon: "fa-truck",
                action: "stock.action_picking_tree_all",
            },
            {
                id: "client_relations",
                label: "Client Relations",
                icon: "fa-handshake-o",
                action: "crm.crm_lead_action_pipeline",
            },
            {
                id: "configuration",
                label: "Configuration",
                icon: "fa-cog",
                action: "base.action_res_users",
            },
        ];
    },

    /**
     * Handle custom navbar item click
     */
    async onCustomNavClick(item) {
        if (!item || !item.action) {
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

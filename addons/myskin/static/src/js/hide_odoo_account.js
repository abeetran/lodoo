/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { UserMenu } from "@web/webclient/user_menu/user_menu";

patch(UserMenu.prototype, {
    setup() {
        super.setup();

        this.items = this.items?.filter(
            (item) => item.id !== "account"
        );
    },
});
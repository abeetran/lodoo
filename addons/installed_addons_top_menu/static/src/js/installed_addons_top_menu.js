/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

import { useService } from "@web/core/utils/hooks";

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";

export class InstalledAppsTopMenu extends Component {

    setup() {
        this.menuService = useService("menu");
        this.state = useState({
            openAppId: null,
            openMenuIds: [],
        });

        console.log(
            "InstalledAppsTopMenu initialized",
            this.menuService
        );
    }

    getMenuService() {
        return this.menuService;
    }


    /**
     * Get all applications.
     */
    get apps() {
        return (this.menuService.getApps() || [])
            .filter((app) => {
                const tree = this.menuService.getMenuAsTree(app.id);
                const children = tree && (tree.childrenTree || tree.children)
                    ? this.filterAllowedMenus(tree.childrenTree || tree.children)
                    : [];
                return children.length > 0;
            });
    }

    isAllowedSubmenu = (menu) => {
        if (!menu) {
            return false;
        }
        return true;
    };

    collectMenuIds = (items, seen = new Set()) => {
        if (!items) {
            return seen;
        }

        const list = Array.isArray(items) ? items : [];

        list.forEach((item) => {
            const menu = typeof item === "number" || typeof item === "string"
                ? this.menuService.getMenu(item)
                : item;

            if (!menu) {
                return;
            }

            const menuId = Number(menu.id);
            if (!Number.isNaN(menuId)) {
                seen.add(menuId);
            }

            this.collectMenuIds(menu.childrenTree || menu.children || [], seen);
        });

        return seen;
    };

    getVisibleMenuChildren = (items) => {
        if (!items) {
            return [];
        }

        const list = Array.isArray(items) ? items : [];
        const result = [];

        list.forEach((item) => {
            const menu = typeof item === "number" || typeof item === "string"
                ? this.menuService.getMenu(item)
                : item;

            if (!menu) {
                return;
            }

            const children = this.getVisibleMenuChildren(menu.childrenTree || menu.children || []);
            const isVisible = children.length > 0 || this.isAllowedSubmenu(menu);

            if (isVisible) {
                result.push({
                    ...menu,
                    childrenTree: children,
                });
            }
        });

        return result;
    };

    filterAllowedMenus = (items) => {
        const visible = this.getVisibleMenuChildren(items);
        const nestedMenuIds = new Set();

        visible.forEach((menu) => {
            this.collectMenuIds(menu.childrenTree || menu.children || [], nestedMenuIds);
        });

        return visible.filter((menu) => !nestedMenuIds.has(Number(menu.id)) || menu.childrenTree?.length > 0);
    };

    isAppOpen = (appId) => {
        return this.state.openAppId === appId;
    };

    toggleApp = (appId) => {
        this.state.openAppId = this.isAppOpen(appId) ? null : appId;
        console.log("[InstalledAppsTopMenu] toggle app:", {
            appId,
            openAppId: this.state.openAppId,
        });
    };

    isMenuOpen = (menuId) => {
        return this.state.openMenuIds.includes(menuId);
    };

    toggleMenu = (menuId) => {
        const ids = this.state.openMenuIds.slice();
        const idx = ids.indexOf(menuId);
        if (idx >= 0) {
            ids.splice(idx, 1);
        } else {
            ids.push(menuId);
        }
        this.state.openMenuIds = ids;
        console.log("[InstalledAppsTopMenu] toggle menu:", {
            menuId,
            openMenuIds: this.state.openMenuIds,
        });
    };

    /**
     * Prepare app menu data in a stable form for the template.
     */
    get appsWithMenus() {
        return (this.menuService.getApps() || [])
            .map((app) => {
                const tree = this.menuService.getMenuAsTree(app.id);
                const menus = tree && (tree.childrenTree || tree.children)
                    ? this.filterAllowedMenus(tree.childrenTree || tree.children)
                    : [];

                console.log("[InstalledAppsTopMenu] app tree:", {
                    app: app?.name,
                    appId: app?.id,
                    rawTree: tree,
                    children: menus,
                });

                return {
                    app,
                    menus,
                };
            })
            .filter(({ menus }) => menus.length > 0);
    }


    /**
     * Select menu.
     *
     * Arrow function keeps `this`.
     */
    selectMenu = (menu) => {

        console.log(
            "[InstalledAppsTopMenu] selecting menu:",
            menu
        );

        if (!menu) {
            return;
        }

        this.menuService.selectMenu(menu);
    };


    /**
     * Generate menu href.
     */
    getMenuHref = (menu) => {

        if (!menu) {
            return "#";
        }

        let href = `#menu_id=${menu.id}`;

        if (menu.actionID) {
            href += `&action=${menu.actionID}`;
        }

        return href;
    };


    /**
     * Check children.
     */
    hasChildren = (menu) => {
        if (!menu) {
            return false;
        }

        const children = this.filterAllowedMenus(menu.childrenTree || menu.children || []);
        return children.length > 0;
    };

    getChildrenTree = (menu) => {
        if (!menu) {
            return [];
        }

        const childrenTree = this.filterAllowedMenus(menu.childrenTree || menu.children || []);
        if (childrenTree.length) {
            return childrenTree;
        }

        return [];
    };
}


InstalledAppsTopMenu.template =
    "installed_addons_top_menu.InstalledAppsTopMenu";


InstalledAppsTopMenu.components = {};


patch(NavBar, {

    components: {
        ...NavBar.components,

        InstalledAppsTopMenu,
    },

});
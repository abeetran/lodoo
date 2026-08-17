# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def load_web_menus(self, debug):
        """
        Rebuild the tree so each app node owns its real submenu entries.
        This is what the custom navbar reads when it does
        menuService.getMenuAsTree(app.id).childrenTree.
        """
        web_menus = super(IrUiMenu, self).load_web_menus(debug)
        if not isinstance(web_menus, dict):
            return web_menus

        for menu_id in list(web_menus.keys()):
            web_menus.setdefault(menu_id, {})
            web_menus[menu_id].setdefault('children', [])

        # Normalize all top-level app children to their app root.
        for menu_id, menu in list(web_menus.items()):
            if menu_id in ('root', None):
                continue

            app_id = menu.get('appID')
            parent_id = menu.get('parentId')

            if app_id and app_id in web_menus and menu_id != app_id:
                app_menu = web_menus[app_id]
                app_menu.setdefault('children', [])
                if menu_id not in app_menu['children']:
                    app_menu['children'].append(menu_id)
                if parent_id not in (None, False, 'root', app_id):
                    menu['parentId'] = app_id
                elif menu.get('parentId') not in (app_id, None, False, 'root'):
                    menu['parentId'] = app_id

            if parent_id in web_menus and parent_id != menu_id:
                parent_menu = web_menus[parent_id]
                parent_menu.setdefault('children', [])
                if menu_id not in parent_menu['children']:
                    parent_menu['children'].append(menu_id)

        return web_menus

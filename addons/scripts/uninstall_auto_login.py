mod = env["ir.module.module"].search([("name", "=", "auth_oauth_auto_login")], limit=1)
if not mod:
    print("[uninstall] auth_oauth_auto_login không có trong DB.")
elif mod.state != "installed":
    print(f"[uninstall] auth_oauth_auto_login state={mod.state}, bỏ qua.")
else:
    mod.button_immediate_uninstall()
    env.cr.commit()
    print("[uninstall] Đã gỡ auth_oauth_auto_login.")

"""Gỡ auth_oauth_auto_login và auth_oauth — SSO qua center_proxy_sso launch token."""
for name in ("auth_oauth_auto_login", "auth_oauth"):
    mod = env["ir.module.module"].search([("name", "=", name)], limit=1)
    if not mod:
        print(f"[uninstall_oauth] {name} khong co trong DB.")
    elif mod.state != "installed":
        print(f"[uninstall_oauth] {name} state={mod.state}, bo qua.")
    else:
        mod.button_immediate_uninstall()
        env.cr.commit()
        print(f"[uninstall_oauth] Da go {name}.")

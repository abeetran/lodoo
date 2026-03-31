import os


def _env(name):
    return (os.getenv(name) or "").strip()


DEFAULT_ADMIN_EMAIL = "phamvanla21009@gmail.com"
DEFAULT_ADMIN_PASSWORD = "vanla@100390"

admin_email = (_env("ODOO_ADMIN_EMAIL") or DEFAULT_ADMIN_EMAIL).lower()
admin_password = _env("ODOO_ADMIN_PASSWORD") or DEFAULT_ADMIN_PASSWORD
admin_name = _env("ODOO_ADMIN_NAME") or "Administrator"

Users = env["res.users"].sudo()
admin_user = Users.browse(2)
if not admin_user.exists():
    admin_user = Users.search([("login", "=", "admin")], limit=1)

if not admin_user:
    print("[admin_bootstrap] Skip: admin user not found.")
else:
    vals = {"login": admin_email, "email": admin_email}
    if admin_name:
        vals["name"] = admin_name
    if admin_password:
        vals["password"] = admin_password

    admin_user.write(vals)
    env.cr.commit()
    print(f"[admin_bootstrap] Admin login set to: {admin_email}")

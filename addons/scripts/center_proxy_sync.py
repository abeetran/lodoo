# Chạy qua: odoo shell -d odoo < center_proxy_sync.py
# Đặt web.base.url = URL public qua center proxy (iframe same-origin).
import os

ICP = env["ir.config_parameter"].sudo()

center_base = (os.environ.get("CENTER_PUBLIC_BASE_URL") or "").strip().rstrip("/")
direct_base = (os.environ.get("SERVICE_URL_ODOO") or "").strip().rstrip("/")

if center_base:
    ICP.set_param("web.base.url", center_base)
    print(f"[center_proxy_sync] web.base.url = {center_base} (center proxy)")
elif direct_base:
    ICP.set_param("web.base.url", direct_base)
    print(f"[center_proxy_sync] web.base.url = {direct_base} (SERVICE_URL_ODOO)")
else:
    print("[center_proxy_sync] Bỏ qua: thiếu CENTER_PUBLIC_BASE_URL và SERVICE_URL_ODOO")

env.cr.commit()

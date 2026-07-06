# Chạy qua: odoo shell -d odoo < center_proxy_sync.py
# Đặt web.base.url = URL public Odoo (SERVICE_URL_ODOO).
import os

ICP = env["ir.config_parameter"].sudo()

direct_base = (os.environ.get("SERVICE_URL_ODOO") or "").strip().rstrip("/")

if direct_base:
    ICP.set_param("web.base.url", direct_base)
    print(f"[center_proxy_sync] web.base.url = {direct_base}")
else:
    print("[center_proxy_sync] Bỏ qua: thiếu SERVICE_URL_ODOO")

env.cr.commit()

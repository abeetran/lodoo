# Chạy qua: odoo shell ... < authentik_icp_sync.py (env do Odoo shell cung cấp)
import os

_required = (
    "AUTHENTIK_CLIENT_ID",
    "AUTHENTIK_CLIENT_SECRET",
    "AUTHENTIK_PUBLIC_URL",
    "AUTHENTIK_INTERNAL_URL",
    "AUTHENTIK_BASE_URL",
    "AUTHENTIK_SLUG",
)
_missing = [k for k in _required if not (os.environ.get(k) or "").strip()]
if _missing:
    print("[authentik_icp_sync] Bỏ qua: thiếu biến môi trường:", ", ".join(_missing))
else:
    ICP = env["ir.config_parameter"].sudo()
    ICP.set_param("authentik.enabled", "1")
    ICP.set_param("authentik.client_id", os.environ["AUTHENTIK_CLIENT_ID"])
    ICP.set_param("authentik.client_secret", os.environ["AUTHENTIK_CLIENT_SECRET"])
    ICP.set_param("authentik.scope", os.environ.get("AUTHENTIK_SCOPE", "openid profile email"))
    ICP.set_param("authentik.public_url", os.environ["AUTHENTIK_PUBLIC_URL"])
    ICP.set_param("authentik.internal_url", os.environ["AUTHENTIK_INTERNAL_URL"])
    ICP.set_param("authentik.base_url", os.environ["AUTHENTIK_BASE_URL"])
    ICP.set_param("authentik.slug", os.environ["AUTHENTIK_SLUG"])
    env.cr.commit()
    print("[authentik_icp_sync] Đã ghi ir.config_parameter từ biến môi trường.")

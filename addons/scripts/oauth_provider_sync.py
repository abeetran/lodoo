# Chạy qua: odoo shell -d odoo < oauth_provider_sync.py
# Tạo/cập nhật auth.oauth.provider từ biến môi trường (giống cấu hình UI Settings → OAuth Providers).
import os

_required = (
    "AUTHENTIK_CLIENT_ID",
    "AUTHENTIK_PUBLIC_URL",
    "SERVICE_URL_ODOO",
)
_missing = [k for k in _required if not (os.environ.get(k) or "").strip()]
if _missing:
    print("[oauth_provider_sync] Bỏ qua: thiếu biến môi trường:", ", ".join(_missing))
else:
    if "auth.oauth.provider" not in env:
        print("[oauth_provider_sync] Bỏ qua: module auth_oauth chưa cài.")
    else:
        base = os.environ["AUTHENTIK_PUBLIC_URL"].strip().rstrip("/")
        slug = (os.environ.get("AUTHENTIK_SLUG") or "").strip().strip("/")
        scope = (os.environ.get("AUTHENTIK_SCOPE") or "openid profile email").strip()
        client_id = os.environ["AUTHENTIK_CLIENT_ID"].strip()
        provider_name = (os.environ.get("OAUTH_PROVIDER_NAME") or "Authentik").strip()
        button_label = (os.environ.get("OAUTH_BUTTON_LABEL") or "Log in with Authentik").strip()

        # Authentik: URL global hoặc theo slug application
        if slug:
            auth_endpoint = f"{base}/application/o/{slug}/authorize/"
            validation_endpoint = f"{base}/application/o/{slug}/userinfo/"
        else:
            auth_endpoint = f"{base}/application/o/authorize/"
            validation_endpoint = f"{base}/application/o/userinfo/"

        ICP = env["ir.config_parameter"].sudo()
        ICP.set_param("web.base.url", os.environ["SERVICE_URL_ODOO"].strip().rstrip("/"))
        # Authentik userinfo cần Bearer token (không chỉ query access_token)
        ICP.set_param("auth_oauth.authorization_header", "1")

        Provider = env["auth.oauth.provider"].sudo()
        provider = Provider.search([("client_id", "=", client_id)], limit=1)
        if not provider:
            provider = Provider.search([("name", "=", provider_name)], limit=1)

        vals = {
            "name": provider_name,
            "client_id": client_id,
            "auth_endpoint": auth_endpoint,
            "validation_endpoint": validation_endpoint,
            "scope": scope,
            "enabled": True,
            "body": button_label,
            "css_class": "fa fa-fw fa-sign-in text-primary",
            "sequence": 1,
        }

        # Tắt provider mặc định Odoo (tránh auto-login nhầm)
        Provider.search([
            ("name", "in", ["Odoo.com Accounts", "Google OAuth2", "Facebook Graph"]),
        ]).write({"enabled": False})

        if provider:
            provider.write(vals)
            print(f"[oauth_provider_sync] Đã cập nhật provider id={provider.id} ({provider_name}).")
        else:
            provider = Provider.create(vals)
            print(f"[oauth_provider_sync] Đã tạo provider id={provider.id} ({provider_name}).")

        # Ép URL tuyệt đối (phòng cấu hình tay chỉ nhập path)
        if provider.auth_endpoint and not provider.auth_endpoint.startswith(("http://", "https://")):
            provider.write({
                "auth_endpoint": auth_endpoint,
                "validation_endpoint": validation_endpoint,
            })

        print(f"[oauth_provider_sync] auth_endpoint={auth_endpoint}")
        print(f"[oauth_provider_sync] validation_endpoint={validation_endpoint}")
        print(f"[oauth_provider_sync] redirect_uri={os.environ['SERVICE_URL_ODOO'].rstrip('/')}/auth_oauth/signin")

        env.cr.commit()

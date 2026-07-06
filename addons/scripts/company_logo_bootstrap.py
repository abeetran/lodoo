import base64
import os

DEFAULT_LOGO = "/mnt/extra-addons/meworld/center_proxy_sso/static/img/zent_logo.png"


def _env(name):
    return (os.getenv(name) or "").strip()


logo_path = _env("COMPANY_LOGO_PATH") or DEFAULT_LOGO
company_name = _env("COMPANY_NAME") or "ZenT"

if not os.path.isfile(logo_path):
    print(f"[company_logo_bootstrap] Skip: khong tim thay file {logo_path}")
else:
    with open(logo_path, "rb") as logo_file:
        logo_b64 = base64.b64encode(logo_file.read())

    Company = env["res.company"].sudo()
    company = Company.search([], limit=1)
    if not company:
        print("[company_logo_bootstrap] Skip: khong co res.company")
    else:
        vals = {"logo": logo_b64}
        if company_name:
            vals["name"] = company_name
        company.write(vals)
        env.cr.commit()
        print(f"[company_logo_bootstrap] Logo updated for company id={company.id} ({company_name})")

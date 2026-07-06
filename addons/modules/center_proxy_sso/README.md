# Center proxy + SSO launch (iframe center manager)

Odoo chạy sau reverse proxy path `/odoo/{tenant_id}/` trên domain center.

## Nginx (center) — gợi ý

```nginx
# TENANT_ID = Mongo tenant id, BACKEND = https://abc123.zent.work
location /odoo/TENANT_ID/ {
    rewrite ^/odoo/TENANT_ID/(.*)$ /$1 break;

    proxy_pass BACKEND;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Script-Name /odoo/TENANT_ID;

    proxy_redirect / /odoo/TENANT_ID/;
    proxy_set_header Accept-Encoding "";

    sub_filter_once off;
    sub_filter 'href="/' 'href="/odoo/TENANT_ID/';
    sub_filter 'src="/' 'src="/odoo/TENANT_ID/';
    sub_filter "url('/" "url('/odoo/TENANT_ID/";
    sub_filter 'url("/' 'url("/odoo/TENANT_ID/';
}

location /odoo/TENANT_ID/websocket {
    rewrite ^/odoo/TENANT_ID/(.*)$ /$1 break;
    proxy_pass BACKEND;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Module Odoo bổ sung: rewrite header `Location` cho redirect nội bộ.

## Test consume token (local, không proxy)

```bash
# Cần JWT_SECRET trong .env container
curl -v "http://localhost:8069/web/sso/consume?token=JWT_HERE"
```

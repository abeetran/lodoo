# Center SSO launch (Zent Manager)

Odoo nhận one-time JWT từ FastAPI Center Manager, tạo session, mở tab mới (không iframe).

## Luồng

1. User đăng nhập Zent Center → bấm **Mở CRM**
2. FastAPI ký JWT (`email`, `tenant_id`, `jti`, `exp`) với `JWT_SECRET` chung
3. Browser mở tab mới: `{SERVICE_URL_ODOO}/web/sso/consume?token=...`
4. Odoo verify JWT, ghi `jti` (one-time), login user → redirect `/web`

## Biến môi trường container

```env
JWT_SECRET=...              # Cùng secret với FastAPI
SERVICE_URL_ODOO=https://trial.example.com
EMAIL_OWNER=user@example.com   # User trial (bootstrap entrypoint)
CENTER_TENANT_ID=...           # Tuỳ chọn — kiểm tra tenant_id trong JWT
```

## Dev: password login

```
/web/login?sso_login=false
```

## Test consume token (local)

```bash
curl -v "http://localhost:8069/web/sso/consume?token=JWT_HERE"
```

#!/bin/bash
set -e

# Tránh cảnh báo Perl/psql khi image không có locale en_US.UTF-8
export LC_ALL=C
export LANG=C

export HOST="${HOST:-db}"
export PASSWORD="${PASSWORD:-odoo}"
export DB_NAME="${DB_NAME:-odoo}"
export PROXY_MODE="${PROXY_MODE:-True}"

# 1. data_dir + sessions (tránh ghi /root/.local/share/Odoo/sessions khi chạy root)
mkdir -p /var/lib/odoo/sessions
chown -R odoo:odoo /var/lib/odoo

# 2. Tạo file config từ template
envsubst '${HOST} ${PASSWORD} ${PROXY_MODE}' < /etc/odoo/odoo.conf.template > /tmp/odoo.conf
mv /tmp/odoo.conf /etc/odoo/odoo.conf
chown odoo:odoo /etc/odoo/odoo.conf

# 3. Chờ Postgres + init DB nếu trống
until PGPASSWORD=$PASSWORD psql -h "$HOST" -U "odoo" -d "postgres" -c '\q'; do
  echo "Đang chờ Postgres ($HOST) sẵn sàng..."
  sleep 2
done

DB_EXISTS=$(PGPASSWORD=$PASSWORD psql -h "$HOST" -U "odoo" -d "$DB_NAME" -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ir_module_module';" 2>/dev/null | tr -d '[:space:]' || echo "0")

if [ "$DB_EXISTS" != "1" ]; then
    echo "Phát hiện Database trống. Đang khởi tạo lần đầu với --init=base..."
    odoo -d "$DB_NAME" --init=base --stop-after-init
    echo "Khởi tạo hoàn tất!"
else
    echo "Database đã có dữ liệu. Bỏ qua khởi tạo để bảo vệ dữ liệu."
fi

# 4. Kiểm tra DB đã sẵn sàng (có bảng ir_module_module)
DB_READY=$(PGPASSWORD=$PASSWORD psql -h "$HOST" -U "odoo" -d "$DB_NAME" -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ir_module_module';" 2>/dev/null | tr -d '[:space:]' || echo "0")

# 4b. Cài app business — chỉ -i module chưa ở trạng thái installed
if [ "$DB_READY" = "1" ]; then
  BUSINESS_MODULES=(crm sale_management calendar account web_session_fix center_proxy_sso)
  TO_INSTALL=""
  for mod in "${BUSINESS_MODULES[@]}"; do
    STATE=$(PGPASSWORD=$PASSWORD psql -h "$HOST" -U "odoo" -d "$DB_NAME" -tAc \
      "SELECT COALESCE(state, 'uninstalled') FROM ir_module_module WHERE name='${mod}';" \
      2>/dev/null | tr -d '[:space:]')
    if [ "$STATE" != "installed" ]; then
      TO_INSTALL="${TO_INSTALL:+$TO_INSTALL,}${mod}"
    fi
  done
  if [ -n "$TO_INSTALL" ]; then
    echo "Đang cài app business: $TO_INSTALL"
    odoo -d "$DB_NAME" -i "$TO_INSTALL" --stop-after-init
  else
    echo "App business đã cài đủ, bỏ qua -i."
  fi
fi

if [ "$DB_READY" = "1" ]; then
  echo "Gỡ auth_oauth / auth_oauth_auto_login (SSO qua Center launch)..."
  odoo shell -d "$DB_NAME" < /mnt/extra-addons/scripts/uninstall_oauth_modules.py || true
fi

if [ "$DB_READY" = "1" ] && { [ -n "${CENTER_PUBLIC_BASE_URL:-}" ] || [ -n "${SERVICE_URL_ODOO:-}" ]; }; then
  echo "Đồng bộ web.base.url (center proxy / SERVICE_URL_ODOO)..."
  odoo shell -d "$DB_NAME" < /mnt/extra-addons/scripts/center_proxy_sync.py
fi

# 5. Bootstrap admin + owner trial (EMAIL_OWNER — user thuong, khong phai admin)
if [ "$DB_READY" = "1" ]; then
  echo "Đang bootstrap tài khoản admin..."
  odoo shell -d "$DB_NAME" < /mnt/extra-addons/scripts/admin_bootstrap.py
fi

if [ "$DB_READY" = "1" ] && { [ -n "${EMAIL_OWNER:-}" ] || [ -n "${TRIAL_USER_EMAIL:-}" ]; }; then
  echo "Đang bootstrap owner trial (EMAIL_OWNER)..."
  odoo shell -d "$DB_NAME" < /mnt/extra-addons/scripts/trial_owner_bootstrap.py
fi

if [ "$DB_READY" = "1" ]; then
  echo "Đang đồng bộ logo công ty (ZenT)..."
  odoo shell -d "$DB_NAME" < /mnt/extra-addons/scripts/company_logo_bootstrap.py
fi

# 6. Thực thi entrypoint gốc của Odoo
exec /entrypoint.sh "$@"

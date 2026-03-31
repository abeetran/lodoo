#!/bin/bash
set -e

# Tránh cảnh báo Perl/psql khi image không có locale en_US.UTF-8
export LC_ALL=C
export LANG=C

export HOST="${HOST:-db}"
export PASSWORD="${PASSWORD:-odoo}"
export DB_NAME="${DB_NAME:-odoo}" # Thêm biến tên DB để linh hoạt

# 1. Xử lý quyền hạn thư mục
mkdir -p /var/lib/odoo
chown -R odoo:odoo /var/lib/odoo

# 2. Tạo file config từ template
envsubst '${HOST} ${PASSWORD}' < /etc/odoo/odoo.conf.template > /tmp/odoo.conf
mv /tmp/odoo.conf /etc/odoo/odoo.conf
chown odoo:odoo /etc/odoo/odoo.conf

# 3. Logic kiểm tra Database để tránh lỗi KeyError 'ir.http'
# Chờ Postgres sẵn sàng trước khi kiểm tra
until PGPASSWORD=$PASSWORD psql -h "$HOST" -U "odoo" -d "postgres" -c '\q'; do
  echo "Đang chờ Postgres ($HOST) sẵn sàng..."
  sleep 2
done

# Kiểm tra xem Database đã được khởi tạo (có bảng ir_module_module) chưa
DB_EXISTS=$(PGPASSWORD=$PASSWORD psql -h "$HOST" -U "odoo" -d "$DB_NAME" -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ir_module_module';" || echo "0")

if [ "$DB_EXISTS" != "1" ]; then
    echo "Phát hiện Database trống. Đang khởi tạo lần đầu với -i base..."
    # Không khởi động HTTP/longpoll khi init (theo Odoo: --no-http) — tránh bind port 8069 / Address already in use
    odoo -d odoo --init=base -i auth_authentik_sso  --stop-after-init
    echo "Khởi tạo hoàn tất!"
else
    echo "Database đã có dữ liệu. Bỏ qua khởi tạo để bảo vệ dữ liệu."
fi

# 4. Đồng bộ Authentik từ biến môi trường -> ir.config_parameter (cần DB đã init)
DB_READY=$(PGPASSWORD=$PASSWORD psql -h "$HOST" -U "odoo" -d "$DB_NAME" -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ir_module_module';" 2>/dev/null | tr -d '[:space:]' || echo "0")

# 4b. Cài app business bằng lệnh riêng (không trộn vào setup lần đầu)
if [ "$DB_READY" = "1" ]; then
  echo "Đang cài app business (nếu chưa có)..."
  odoo -d odoo -i crm,sale_management,calendar,website,account --stop-after-init
fi

if [ "$DB_READY" = "1" ] && [ -n "${AUTHENTIK_CLIENT_ID:-}" ]; then
  echo "Đồng bộ cấu hình Authentik (ir.config_parameter)..."
  odoo shell -d odoo < /mnt/extra-addons/meworld/authentik_icp_sync.py
fi

# 5. Bootstrap admin login theo email (có default nếu thiếu env)
if [ "$DB_READY" = "1" ]; then
  echo "Đang bootstrap tài khoản admin..."
  odoo shell -d odoo < /mnt/extra-addons/meworld/admin_bootstrap.py
fi

# 6. Thực thi entrypoint gốc của Odoo (Chạy Odoo bình thường)
exec /entrypoint.sh "$@"

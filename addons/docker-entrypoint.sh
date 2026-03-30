#!/bin/bash
set -e

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
DB_EXISTS=$(PGPASSWORD=$PASSWORD psql -h "$HOST" -U "odoo" -d odoo -tAc "SELECT 1 FROM information_schema.tables WHERE table_name='ir_module_module';" || echo "0")

if [ "$DB_EXISTS" != "1" ]; then
    echo "Phát hiện Database trống. Đang khởi tạo lần đầu với -i base..."
    # Chạy init một lần rồi dừng
    sudo odoo -i base --stop-after-init
    echo "Khởi tạo hoàn tất!"
else
    echo "Database đã có dữ liệu. Bỏ qua khởi tạo để bảo vệ dữ liệu."
fi

# 4. Thực thi entrypoint gốc của Odoo (Chạy Odoo bình thường)
exec /entrypoint.sh "$@"

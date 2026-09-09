#!/bin/bash
# Deploy crall_material (or another module) without missing-column/menu errors.
# Usage: ./deploy.sh [db_name] [module_name]   (defaults: lodooo crall_material)
set -e
cd "$(dirname "$0")"

DB="${1:-lodooo}"
MODULE="${2:-crall_material}"
LOG="/tmp/odoo-upgrade-${MODULE}.log"

echo "==> [1/5] Building odoo image (bakes ./addons into the container)..."
docker compose build odoo

echo "==> [2/5] Starting containers..."
docker compose up -d odoo

echo "==> [3/5] Waiting for PostgreSQL..."
until docker compose exec -T db pg_isready -U odoo >/dev/null 2>&1; do sleep 2; done

echo "==> [4/5] Upgrading module '${MODULE}' on database '${DB}'..."
docker compose exec -T odoo odoo -u "$MODULE" -d "$DB" --stop-after-init 2>&1 | tee "$LOG"
if grep -qi "traceback" "$LOG"; then
    echo "!!! UPGRADE FAILED - see $LOG. Container left stopped; fix the error and re-run."
    exit 1
fi

echo "==> [5/5] Starting Odoo back up..."
docker compose up -d odoo

echo "==> Verify:"
docker compose exec -T db psql -U odoo -d "$DB" -tAc \
    "SELECT name, latest_version FROM ir_module_module WHERE name = '$MODULE';"
echo "Done. Hard-refresh the browser (Ctrl+Shift+R). Full log: $LOG"

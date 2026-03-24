#!/bin/bash
set -e
export HOST="${HOST:-db}"
export PASSWORD="${PASSWORD:-odoo}"

# Bind mount (Coolify/host) thường là root; Odoo cần ghi /var/lib/odoo
mkdir -p /var/lib/odoo
chown -R odoo:odoo /var/lib/odoo

envsubst '${HOST} ${PASSWORD}' < /etc/odoo/odoo.conf.template > /tmp/odoo.conf
mv /tmp/odoo.conf /etc/odoo/odoo.conf
chown odoo:odoo /etc/odoo/odoo.conf

exec /entrypoint.sh "$@"

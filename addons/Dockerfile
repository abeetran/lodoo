FROM odoo:17

USER root

# Copy custom addons
COPY . /mnt/extra-addons/meworld

# Copy config if any
# COPY config/odoo.conf /etc/odoo/odoo.conf

RUN chown -R odoo:odoo /mnt/extra-addons /etc/odoo

USER odoo
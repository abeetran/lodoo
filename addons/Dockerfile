FROM odoo:17

USER root

# Copy custom addons
COPY . /mnt/extra-addons/meworld

# Drop stale bytecode so the container never runs cached .pyc
# from a previous copy of the sources
RUN find /mnt/extra-addons -name __pycache__ -type d -exec rm -rf {} +

# Copy config if any
# COPY config/odoo.conf /etc/odoo/odoo.conf

RUN chown -R odoo:odoo /mnt/extra-addons /etc/odoo

USER odoo
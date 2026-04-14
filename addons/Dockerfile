FROM odoo:17

USER root

# Install đầy đủ SCSS compiler (QUAN TRỌNG)
RUN pip3 install libsass
RUN apt-get update && apt-get install -y sassc

# Copy custom addons
COPY . /mnt/extra-addons

# Copy config if any
COPY config/odoo.conf /etc/odoo/odoo.conf

RUN chown -R odoo:odoo /mnt/extra-addons /etc/odoo

USER odoo
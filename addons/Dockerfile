FROM odoo:17

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base \
    && rm -rf /var/lib/apt/lists/*

COPY odoo.conf.template /etc/odoo/odoo.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

COPY . /mnt/extra-addons/meworld

RUN chown -R odoo:odoo /mnt/extra-addons /etc/odoo

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["odoo"]

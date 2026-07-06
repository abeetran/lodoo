FROM odoo:17

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base \
    && rm -rf /var/lib/apt/lists/*

COPY docker/odoo.conf.template /etc/odoo/odoo.conf.template
COPY docker/docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

COPY modules/ /mnt/extra-addons/meworld/
COPY scripts/ /mnt/extra-addons/scripts/

RUN chown -R odoo:odoo /mnt/extra-addons /etc/odoo

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["odoo", "-d", "odoo"]

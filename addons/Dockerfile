FROM odoo:17

USER root

# install python dependencies for OpenEduCat
RUN pip3 install \
    num2words \
    phonenumbers \
    xlrd \
    xlwt \
    XlsxWriter \
    reportlab \
    python-dateutil \
    pytz \
    requests \
    Pillow \
    lxml \
    qrcode

# copy custom addons
COPY . /mnt/extra-addons

# fix permission
RUN chown -R odoo:odoo /mnt/extra-addons

USER odoo
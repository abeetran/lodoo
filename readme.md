# run docker
  docker compose up -d
# authentik registration
  http://localhost:9000/if/flow/initial-setup/
# setup authentik
  http://localhost:9000


## config addons/auth_authentik_sso
  replace 'authentik' in controller/main.py by your slug from provider of authentik


# setup database
docker exec -it odoo_tik odoo shell -d lodooo

ICP = env['ir.config_parameter'].sudo()
ICP.set_param('authentik.enabled', '1')
ICP.set_param('authentik.base_url', 'https://authentikserver.bms360.cloud')  # sửa localhost -> authentik-server
ICP.set_param('authentik.client_id', 'y7Dt2FeprIpNcfTkhPRjy59JVEns7Ay2Btds6n4m')
ICP.set_param('authentik.client_secret', 'XLWaUx6G20zYYXtMfNnXVyy2TTDDrX5kkULD65FawdZ2EfGwDGgKUm5UBbCgf31zOZNm4GFVDYIX8W8D4TQx0YduQZdZo7usjGdBNstZjokGwC1MzynlZfOtY2q8Gvza')
ICP.set_param('authentik.scope', 'openid profile email')

exit()



docker compose exec odoo bash -lc "odoo shell -d odoo17 -c /etc/odoo/odoo.conf <<'PY'
env['ir.config_parameter'].sudo().set_param('authentik.enabled', '1')
env['ir.config_parameter'].sudo().set_param('authentik.base_url', 'http://localhost:9000')
print('enabled=', env['ir.config_parameter'].sudo().get_param('authentik.enabled'))
print('base_url=', env['ir.config_parameter'].sudo().get_param('authentik.base_url'))
PY"


docker compose exec db psql -U odoo -d postgres -tAc "SELECT datname FROM pg_database WHERE datistemplate = false;"


docker compose exec odoo bash -lc "odoo shell -d lodooo -c /etc/odoo/odoo.conf <<'PY'
ICP = env['ir.config_parameter'].sudo()
ICP.set_param('authentik.enabled', '1')
ICP.set_param('authentik.base_url', 'http://localhost:9000')
print('authentik.enabled =', ICP.get_param('authentik.enabled'))
print('authentik.base_url =', ICP.get_param('authentik.base_url'))
PY"

docker compose exec db psql -U odoo -d lodooo -c "
INSERT INTO ir_config_parameter(key, value)
VALUES ('authentik.slug', 'lotusauth')
ON CONFLICT (key) DO UPDATE SET value='lotusauth';
"

server psql -U odoo -d postgres
docker compose exec db psql -U odoo -d lodooo -c "
INSERT INTO ir_config_parameter(key, value)
VALUES ('authentik.client_id', 'Q25hRVKZFlDkpTcM2JUnBT06rcal8j0fYfn7mToW')
ON CONFLICT (key) DO UPDATE SET value='Q25hRVKZFlDkpTcM2JUnBT06rcal8j0fYfn7mToW';
"

container lotus:
odoo shell -d odoo
env['ir.config_parameter'].sudo().set_param(
    'authentik.client_id',
    'Q25hRVKZFlDkpTcM2JUnBT06rcal8j0fYfn7mToW'
)
env['ir.config_parameter'].sudo().set_param(
    'authentik.client_secret',
    'LVssewgtNO5fah3r8cbhqqqIMnJUG61XaxzsZqRdmTneuTSVMSAN3f8o1O1OvkmpE4FkaDIBP5RMFdp1GRn9bLLfftSYp5HXQFUHedyVPV2G0ppO7tohCv7z3zMORQTk'
)

restart coolify container:
terminal run: pkill -f odoo

server psql -U odoo -d postgres
docker compose exec db psql -U odoo -d lodooo -c "
INSERT INTO ir_config_parameter(key, value)
VALUES ('authentik.client_secret', 'LVssewgtNO5fah3r8cbhqqqIMnJUG61XaxzsZqRdmTneuTSVMSAN3f8o1O1OvkmpE4FkaDIBP5RMFdp1GRn9bLLfftSYp5HXQFUHedyVPV2G0ppO7tohCv7z3zMORQTk')
ON CONFLICT (key) DO UPDATE SET value='LVssewgtNO5fah3r8cbhqqqIMnJUG61XaxzsZqRdmTneuTSVMSAN3f8o1O1OvkmpE4FkaDIBP5RMFdp1GRn9bLLfftSYp5HXQFUHedyVPV2G0ppO7tohCv7z3zMORQTk';
"

docker compose exec db psql -U odoo -d lodooo -c "
INSERT INTO ir_config_parameter(key, value)
VALUES ('authentik.base_url', 'http://localhost:9000')
ON CONFLICT (key) DO UPDATE SET value='http://localhost:9000';
"




## Note:
in case can not run and show: "failed to connect to authentik backend: authentik starting"

docker exec -it odoo_tik odoo shell -d lodooo
ICP = env['ir.config_parameter'].sudo()
print("base_url =", ICP.get_param('authentik.base_url'))

# Set lại đúng base_url
ICP.set_param('authentik.base_url', 'http://authentik-server:9000')
ICP.set_param('authentik.enabled', '1')

# Reset
docker restart odoo_tik

# vào odoo shell
docker exec -it odoo_tik odoo shell -d lodooo
psql -U odoo -d postgres
ICP = env['ir.config_parameter'].sudo()
ICP.set_param('authentik.enabled', '1')
ICP.set_param('authentik.client_id', 'y7Dt2FeprIpNcfTkhPRjy59JVEns7Ay2Btds6n4m')
ICP.set_param('authentik.client_secret', 'XLWaUx6G20zYYXtMfNnXVyy2TTDDrX5kkULD65FawdZ2EfGwDGgKUm5UBbCgf31zOZNm4GFVDYIX8W8D4TQx0YduQZdZo7usjGdBNstZjokGwC1MzynlZfOtY2q8Gvza')
ICP.set_param('authentik.scope', 'openid profile email')
ICP.set_param('authentik.public_url', 'https://authentikserver.bms360.cloud')          # Browser -> Authentik (host)
ICP.set_param('authentik.internal_url', 'https://authentikserver.bms360.cloud')  # Odoo -> Authentik
ICP.set_param('authentik.base_url', 'https://authentikserver.bms360.cloud')     # fallback

exit()

# Reset
docker restart odoo_tik


## return false khi chạy ICP.set_param('authentik.internal_url', 'http://authentik-server:9000')
docker exec -it odoo_tik odoo shell -d lodooo
ICPModel = env['ir.config_parameter'].sudo()

def force_set(key, value):
    rec = ICPModel.search([('key', '=', key)], limit=1)
    if rec:
        rec.write({'value': value})
    else:
        ICPModel.create({'key': key, 'value': value})
    env.cr.commit()
    return ICPModel.get_param(key)

force_set('authentik.public_url', 'https://authentikserver.bms360.cloud')
force_set('authentik.internal_url', 'https://authentikserver.bms360.cloud')
force_set('authentik.base_url', 'https://authentikserver.bms360.cloud')

# nếu không ghi được db
env.cr.rollback()

tiếp là sử dụng Alternative: update bằng SQL (cứng nhất)
docker exec -it odoo_db psql -U odoo -d lodooo

INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date)
VALUES ('authentik.public_url', 'http://localhost:9000', 1, 1, now(), now())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_uid=1, write_date=now();

INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date) VALUES ('authentik.internal_url', 'https://authentikserver.bms360.cloud', 1, 1, now(), now()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_uid=1, write_date=now();


## set param if still error
ICP = env['ir.config_parameter'].sudo()
ICP.set_param('authentik.slug', 'authserv')


# OPENAI_API_KEY
👉 https://platform.openai.com/signup
👉 https://platform.openai.com/api-keys
  Create new secret key


  INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date) VALUES ('authentik.enabled', '1', 1, 1, now(), now()),('authentik.client_id', 'y7Dt2FeprIpNcfTkhPRjy59JVEns7Ay2Btds6n4m', 1, 1, now(), now()),('authentik.client_secret', 'XLWaUx6G20zYYXtMfNnXVyy2TTDDrX5kkULD65FawdZ2EfGwDGgKUm5UBbCgf31zOZNm4GFVDYIX8W8D4TQx0YduQZdZo7usjGdBNstZjokGwC1MzynlZfOtY2q8Gvza', 1, 1, now(), now()),('authentik.scope', 'openid profile email', 1, 1, now(), now()),('authentik.public_url', 'https://authentikserver.bms360.cloud', 1, 1, now(), now()),('authentik.internal_url', 'https://authentikserver.bms360.cloud', 1, 1, now(), now()),('authentik.base_url', 'https://authentikserver.bms360.cloud', 1, 1, now(), now()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_uid = 1, write_date = now();
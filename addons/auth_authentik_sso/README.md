# Authentik SSO Login for Odoo

## Features
- Login button on Odoo login page
- OAuth2/OIDC login using Authentik
- Auto-create user on first login
- Restrict login by email domain (optional)

## Config
Settings -> General Settings -> Authentik SSO
- Enable
- Base URL (https://authentik.example.com)
- Client ID / Secret
- Redirect URI:
  https://<odoo-domain>/auth/authentik/callback

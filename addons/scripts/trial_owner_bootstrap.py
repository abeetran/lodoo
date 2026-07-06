import os


def _env(name):
    return (os.getenv(name) or "").strip()


owner_email = (_env("EMAIL_OWNER") or _env("TRIAL_USER_EMAIL")).lower()
owner_password = _env("TRIAL_USER_PASSWORD") or _env("EMAIL_OWNER_PASSWORD") or "TrialUser@123"
owner_name = _env("EMAIL_OWNER_NAME") or (owner_email.split("@")[0] if owner_email else "Trial User")

if not owner_email:
    print("[trial_owner_bootstrap] Skip: thieu EMAIL_OWNER / TRIAL_USER_EMAIL")
else:
    Users = env["res.users"].sudo()
    group_user = env.ref("base.group_user")
    group_system = env.ref("base.group_system")

    user = Users.search([("login", "=ilike", owner_email)], limit=1)
    if not user:
        user = Users.search([("email", "=ilike", owner_email)], limit=1)

    if user and user.id == 2:
        print("[trial_owner_bootstrap] Skip: EMAIL_OWNER trung admin (id=2) — tach admin va owner")
    elif user:
        vals = {"login": owner_email, "email": owner_email}
        if group_system in user.groups_id:
            vals["groups_id"] = [(3, group_system.id), (4, group_user.id)]
        user.write(vals)
        env.cr.commit()
        print(f"[trial_owner_bootstrap] Owner user ready: {owner_email}")
    else:
        Users.create(
            {
                "name": owner_name,
                "login": owner_email,
                "email": owner_email,
                "password": owner_password,
                "groups_id": [(6, 0, [group_user.id])],
            }
        )
        env.cr.commit()
        print(f"[trial_owner_bootstrap] Created owner user (internal): {owner_email}")

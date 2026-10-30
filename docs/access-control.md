# Access control: roles & permissions, two-factor, SSO

Escalated's roles & permissions, two-factor authentication and single sign-on
are **install-level switches**, off by default
([ADR 2026-10-29](https://github.com/escalated-dev/escalated-developer-context/blob/main/decisions/2026-10-29-configurable-access-features.md)).
While a switch is off its screens and routes answer 404 and nothing is
enforced; Escalated's admin check (`is_staff` / `is_superuser`) and agent check
(department membership) decide who may do what, exactly as before. While it is
on, the feature is enforced.

The switches are read from `ESCALATED["ACCESS"]` in your settings, else the
environment. No admin screen or stored setting changes them.

| Feature | Setting | Env var |
|---|---|---|
| Roles & permissions | `ESCALATED["ACCESS"]["roles_permissions"]` | `ESCALATED_ROLES_PERMISSIONS` |

```python
ESCALATED = {
    # ...
    "ACCESS": {"roles_permissions": True},
}
```

## Roles & permissions

### What is enforced

With the switch on, every admin, agent and staff API view needs a permission
**in addition to** the admin or agent check for that area. A user's
permissions are the union of their Escalated roles' permissions. Nothing else
grants one: `is_staff` or `is_superuser` gives no permissions by itself. Give
users who should have everything the `admin` role.

- The URL name to permission map is `escalated/access.py`
  (escalated-laravel's `RoutePermissions`). A staff URL missing from it is
  refused, and a test walks the URL conf so a new one cannot ship unguarded or
  unmapped. A write (POST and the like) to a screen whose read needs
  `<group>.view` needs `<group>.manage`.
- A status change needs `ticket.edit`, plus `ticket.close` when the new status
  is `resolved`, `closed` or `reopened`.
- Bulk actions need the permission of the action: `assign` needs
  `ticket.assign`, `delete` needs `ticket.delete`, `close` needs `ticket.close`,
  the rest `ticket.edit`.
- Applying a macro needs `macro.view` and `ticket.edit`; an internal API reply
  needs `reply.create_internal`.
- API tokens act as their owner, so the staff API checks the owner's
  permissions as well as the token's abilities.
- The newsletter screens check `newsletters.manage` and `newsletters.send`, and
  plugin menu items and widgets check their `permission`, only while the switch
  is on.
- Your own two-factor screens need no permission.

Failing a permission answers 403.

### Seeded roles

`python manage.py seed_permissions` creates the permissions and three system
roles:

| Role | Permissions |
|---|---|
| `admin` | all |
| `agent` | `ticket.*`, `reply.*`, `kb.view`, `report.view`, `macro.view`, `macro.create`, `tag.view`, `custom_field.view`, `audit.view` |
| `light_agent` | `ticket.view`, `reply.create`, `reply.create_internal`, `kb.view`, `macro.view`, `tag.view` |

Custom roles are made in **Admin > Roles**, which exists while the switch is on.

### Turning it on

1. `python manage.py seed_permissions`
2. Give every staff user a role, starting with yourself:
   `python manage.py assign_role you@example.com admin` (email, username or id).
3. Set `ESCALATED["ACCESS"] = {"roles_permissions": True}` or
   `ESCALATED_ROLES_PERMISSIONS=true`.

Staff without a role can still reach their personal screens and nothing else.

### Shared props

Every page gets `escalated.features.roles_permissions` (boolean) and
`escalated.permissions`: the user's slugs while on, `['*']` for staff while
off, `[]` for everyone else.

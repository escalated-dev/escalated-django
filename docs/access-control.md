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
| Two-factor authentication | `ESCALATED["ACCESS"]["two_factor"]` | `ESCALATED_TWO_FACTOR` |

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

## Two-factor authentication

### What is enforced

With `ESCALATED_TWO_FACTOR=true` (after `python manage.py migrate escalated`):

- TOTP is RFC 6238 (SHA-1, 6 digits, 30 s) through `pyotp`, with one step of
  drift either side. A code's time step is recorded when it is accepted, and
  that step or an earlier one is refused afterwards.
- A staff user with a confirmed enrolment who opens any admin or agent view
  without having passed the challenge in this session is redirected to
  `GET /support/two-factor/challenge/` (`Escalated/Auth/TwoFactorChallenge`,
  props `action` and `error`). JSON requests get
  `403 {"two_factor_required": true}`.
- The challenge posts `code` or `recovery_code` to the same URL. Success
  cycles the session key, marks the session for that user and returns to the
  page they asked for. Failure is a validation error on the field sent. Five
  attempts per user per minute (Django's cache); then 429.
- Every login is challenged again: the mark is cleared on Django's
  `user_logged_in` and `user_logged_out` signals.
- Eight single-use recovery codes are issued at setup; a code that signs
  someone in is removed. Secrets and recovery codes are sealed at rest with a
  key derived from `SECRET_KEY`; enrolments stored before are read as they are.
- Enrolment (`/support/admin/settings/two-factor/`, and `setup/`, `confirm/`,
  `disable/`) is open to every staff user, not only admins, and needs no
  permission. Confirming marks the session as passed.
- The token API is not session-based and is not challenged.

### Requiring it

`ESCALATED["TWO_FACTOR"] = {"REQUIRED": True}` (`ESCALATED_TWO_FACTOR_REQUIRED`),
or the `two_factor_required` setting (posted to `admin/settings/update/`; the
setting wins once saved). When required, a staff user without an enrolment is
sent to enrol and can use nothing else until they do. Pages get
`escalated.two_factor_required`.

### Lost device

`python manage.py reset_two_factor user@example.com` removes a user's
enrolment.

### While it is off

The enrolment and challenge routes answer 404 and nobody is challenged.
Enrolments are kept.

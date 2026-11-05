# Embedding the admin in your own admin panel (optional)

Escalated ships a complete standalone admin at `/support/admin/` (wherever you
`include("escalated.urls")`, plus `admin/`), with its own sidebar and top bar.
**That is the default, and it needs no setup.** If your Django project already
has an admin panel or back office, you can instead show Escalated's admin
screens inside it: under your sidebar and header, your URL prefix and your
access checks.

This is an optional alternative to the standalone admin. Nothing on this page
has any effect until you turn it on: with no `ESCALATED["EMBED"]` setting every
URL, page, prop, template and header is exactly what it was before (a test
compares the whole URL table with the one from before this feature). The
design is in the ADR
[`2026-11-05-embeddable-admin`](https://github.com/escalated-dev/escalated-developer-context/blob/main/decisions/2026-11-05-embeddable-admin.md);
the frontend side is documented in
[`@escalated-dev/escalated` docs/embedding-admin.md](https://github.com/escalated-dev/escalated/blob/main/docs/embedding-admin.md).

## Contents

- [Pick your setup](#pick-your-setup)
- [Turning it on](#turning-it-on)
- [Configuration reference](#configuration-reference)
- [What changes, and what does not](#what-changes-and-what-does-not)
- [1. Vue + Inertia host](#1-vue--inertia-host)
- [2. Django template host](#2-django-template-host)
- [3. iframe](#3-iframe)
- [The admin menu: `escalated.navigation`](#the-admin-menu-escalatednavigation)
- [Security](#security)
- [What does not move](#what-does-not-move)
- [Turning it off](#turning-it-off)

## Pick your setup

| Your admin panel | Use | `MODE` |
|---|---|---|
| Vue + Inertia in this project | [Vue + Inertia host](#1-vue--inertia-host) | `"layout"` |
| Django templates (your back office's base template) | [Django template host](#2-django-template-host) (your template as the Inertia root view) | `"layout"` |
| Another app or origin, a non-Vue SPA, a CMS admin | [iframe](#3-iframe) | `"iframe"` |

## Turning it on

Two steps, both in your project.

**1. The setting.** Add `EMBED` to your `ESCALATED` settings, either with the
`embed_admin()` helper:

```python
# settings.py
from escalated.embed import embed_admin

ESCALATED = {
    # ...your existing Escalated settings...
    "EMBED": embed_admin(
        prefix="admin/support",
        middleware=["django.contrib.admin.views.decorators.staff_member_required"],
        layout="Layouts/AdminLayout",
    ),
}
```

or as a plain dict (keys you leave out keep their defaults):

```python
ESCALATED = {
    # ...
    "EMBED": {
        "ENABLED": True,
        "MODE": "layout",
        "PREFIX": "admin/support",
        "MIDDLEWARE": ["django.contrib.admin.views.decorators.staff_member_required"],
        "REPLACE_ADMIN_GATE": False,
        "LAYOUT": "Layouts/AdminLayout",
        "ROOT_VIEW": None,
        "FRAME_ANCESTORS": [],
    },
}
```

or with environment variables (`ESCALATED_EMBED=true`,
`ESCALATED_EMBED_PREFIX=admin/support`, ...) for the keys the setting leaves
out.

**2. The URLconf.** Django mounts an `include()` under one prefix, and the
admin now lives under a different one, so include `escalated.embed_urls` at the
site root in place of `escalated.urls`:

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    # ...
    # path("support/", include("escalated.urls")),  # the standalone admin
    path("", include("escalated.embed_urls")),
]
```

`escalated.embed_urls` serves everything `escalated.urls` does under
`ESCALATED["ROUTE_PREFIX"]` (default `"support"`, so `/support/...`), except the
admin, which it serves under `PREFIX`. Keep `ROUTE_PREFIX` equal to the prefix
you used to include `escalated.urls` (the shared frontend already builds agent
panel links from it). `python manage.py check` warns (`escalated.W001`) when
embedding is on but the admin is not mounted.

## Configuration reference

| Key (`ESCALATED["EMBED"][...]`) | Env var | Default | Meaning |
|---|---|---|---|
| `ENABLED` | `ESCALATED_EMBED` | `False` | Master switch. While `False`, nothing below has any effect. |
| `MODE` | `ESCALATED_EMBED_MODE` | `"layout"` | `"layout"` (Vue + Inertia or Django template host) or `"iframe"`. |
| `PREFIX` | `ESCALATED_EMBED_PREFIX` | `"admin/support"` | URL prefix the admin moves under, from the site root. |
| `MIDDLEWARE` | | `None` | View decorators (callables or dotted paths) run on every admin view before Escalated's own guards, first listed outermost. `None` adds none: the admin views keep their own sign-in and admin checks. |
| `REPLACE_ADMIN_GATE` | | `False` | `True` removes Escalated's admin gate from these views so your `MIDDLEWARE` alone decides. Needs `MIDDLEWARE`. See [Security](#security). |
| `LAYOUT` | | `None` | Name of your Vue admin layout, matched against the frontend plugin's `layouts` option. |
| `ROOT_VIEW` | | `None` | Template used as the Inertia root view (in place of `INERTIA_LAYOUT`) on embedded pages ([Django template host](#2-django-template-host)). |
| `FRAME_ANCESTORS` | `ESCALATED_EMBED_FRAME_ANCESTORS` (comma-separated) | `[]` | iframe mode: exact origins allowed to frame the admin. `*`, wildcards, paths and anything not `http(s)` are ignored. |

Keys may be upper or lower case. `embed_admin(prefix=, middleware=, layout=,
root_view=, mode=, replace_admin_gate=, frame_ancestors=)` returns the same
dict with `ENABLED: True`, and refuses an unknown `mode` or
`replace_admin_gate=True` without `middleware`.

"Middleware" here means view decorators, as Django middleware applies to every
request. Any decorator taking a view works: `login_required`,
`staff_member_required`, `permission_required("backoffice.view")` from a module
of yours, or your own. A decorator that answers (a redirect, a 403) stops the
request before Escalated runs.

## What changes, and what does not

While embedding is on:

- Every admin URL that lived under `/support/admin/` (the admin screens, plugin
  admin, API tokens, import, settings) and the SDK plugins' admin pages are
  served under your `PREFIX`, through your `MIDDLEWARE` decorators, then
  Escalated's own guards (the admin gate unless you replace it, two-factor,
  route permissions). **URL names do not change**, so `reverse()`, redirects
  and the `ziggy` route table the shared frontend reads (`route('escalated.admin.…')`)
  follow. The old `/support/admin/...` URLs answer 404.
- Embedded pages carry `escalated.embed`, and every Inertia page carries
  `escalated.navigation`, the admin menu for your sidebar.

`escalated.embed` on an embedded page:

```json
{
  "enabled": true,
  "mode": "layout",
  "layout": "Layouts/AdminLayout",
  "route": "escalated.admin.tickets.index",
  "base_url": "/admin/support",
  "allowed_origins": []
}
```

`route` is the page's name in the `ziggy` table the frontend reads
(`escalated.admin.tickets.index`), or the Django view name
(`escalated:admin_...`) for a page that table does not list. On every other page
`enabled` is `false` and `route` is `null`.

## 1. Vue + Inertia host

Backend: turn embedding on ([above](#turning-it-on)) with your prefix, your
admin decorators and `LAYOUT`.

Frontend: register your admin layout under the name you gave `LAYOUT`, or add
`admin` to the plugin's `layoutScope`:

```js
// frontend/main.js
import { createApp, h } from 'vue'
import { createInertiaApp } from '@inertiajs/vue3'
import { EscalatedPlugin } from '@escalated-dev/escalated'
import AdminLayout from './layouts/AdminLayout.vue'
import BaseLayout from './layouts/BaseLayout.vue'

createInertiaApp({
  resolve: name => { /* the Escalated page resolver from the README */ },
  setup({ el, App, props, plugin }) {
    createApp({ render: () => h(App, props) })
      .use(plugin)
      .use(EscalatedPlugin, {
        layout: BaseLayout,                              // customer pages, as before
        layouts: { 'Layouts/AdminLayout': AdminLayout }, // embedded admin pages
        theme: { panel: { mode: 'light' } },             // match your admin
      })
      .mount(el)
  },
})
```

Your admin layout needs the slots the plugin's `layout` always required, a
`#header` slot (Escalated puts the page title there) and a default slot. List
Escalated's menu with `<EscalatedNavigation />`:

```vue
<!-- frontend/layouts/AdminLayout.vue -->
<script setup>
import { EscalatedNavigation } from '@escalated-dev/escalated'
</script>

<template>
  <div class="flex min-h-screen">
    <aside class="w-64 border-r bg-white p-3">
      <a href="/backoffice/">Dashboard</a>
      <!-- …your own items… -->
      <p class="mt-4 px-3 text-xs font-semibold uppercase text-gray-500">Support</p>
      <EscalatedNavigation />
    </aside>
    <div class="flex-1">
      <header class="border-b bg-white px-6 py-4"><slot name="header" /></header>
      <main class="p-6"><slot /></main>
    </div>
  </div>
</template>
```

Escalated renders each admin page chrome-free (no Escalated sidebar, top bar,
logo or footer) inside your layout. `useEscalatedNavigation()` gives the same
items as computed refs if you draw the menu yourself. To use the layout for
customer pages too, use `layout: AdminLayout, layoutScope: ['customer', 'admin']`
instead of `layouts`.

## 2. Django template host

If your back office is Django templates, make a template that contains your
chrome and Inertia's `{% block inertia %}`, and point `ROOT_VIEW` at it:

```python
ESCALATED = {
    # ...
    "EMBED": embed_admin(
        prefix="backoffice/helpdesk",
        middleware=["django.contrib.admin.views.decorators.staff_member_required"],
        root_view="backoffice/escalated.html",
    ),
}
```

```django
{# templates/backoffice/escalated.html #}
{% load escalated_embed escalated_routes %}<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Back office</title>
    {% escalated_route_helper %}
</head>
<body>
    <header class="backoffice-header">Host Back Office</header>
    <div class="backoffice">
        <aside>
            <a href="/backoffice/">Dashboard</a>
            <p class="menu-heading">Support</p>
            {% escalated_admin_navigation as support_menu %}
            <ul>
                {% for item in support_menu %}
                    <li><a href="{{ item.url }}"{% if item.active %} class="active" aria-current="page"{% endif %}>{{ item.label }}</a></li>
                {% endfor %}
            </ul>
        </aside>
        <main>{% block inertia %}{% endblock %}</main>
    </div>
</body>
</html>
```

Add your own `<script>`/`<link>` tags (django-vite, webpack loader...) and the
`csrf-token` meta tag from the README's CSRF section, as in your
`INERTIA_LAYOUT`. This is the template the test suite renders
(`tests/templates/backoffice/escalated.html`).

`{% escalated_admin_navigation as items %}` gives the menu for the request's
user (it needs the `request` context processor); pass a user to choose another
(`{% escalated_admin_navigation some_user as items %}`). In Python,
`escalated.embed.admin_navigation(user, request)` returns the same list.

Only embedded pages use this template; every other Escalated page keeps your
`INERTIA_LAYOUT`. Your Inertia entry needs no extra option: Escalated sees
`escalated.embed.enabled` and renders the page chrome-free (title and
content). `ROOT_VIEW` applies to the built-in Inertia renderer; a custom
`ESCALATED["UI_RENDERER"]` decides its own template.

## 3. iframe

For an admin that is not part of this project (another origin, another
stack), frame the embedded admin:

```python
ESCALATED = {
    # ...
    "EMBED": embed_admin(
        prefix="admin/support",
        middleware=["django.contrib.admin.views.decorators.staff_member_required"],
        mode="iframe",
        frame_ancestors=["https://admin.example.com"],
    ),
}

MIDDLEWARE = [
    "escalated.middleware.EscalatedEmbedMiddleware",  # first
    # ...the rest, unchanged...
]
```

or `ESCALATED_EMBED=true`, `ESCALATED_EMBED_MODE=iframe`,
`ESCALATED_EMBED_FRAME_ANCESTORS=https://admin.example.com`.

Embedded responses then carry
`Content-Security-Policy: frame-ancestors 'self' https://admin.example.com`
and no `X-Frame-Options` (the allow-listed `frame-ancestors` replaces it on
those responses only; Django's `XFrameOptionsMiddleware` keeps protecting
every other page). `EscalatedEmbedMiddleware` goes **first** in `MIDDLEWARE`
so it sees each response after every other middleware: one of yours that adds
`X-Frame-Options` or replaces the CSP cannot undo it (`manage.py check` warns,
`escalated.W002`, when it is not first). A CSP your project already sends is
kept and this directive is added as a second policy; if your own policy has a
`frame-ancestors` directive, list the same origins there too, since browsers
enforce both.

On the framing page:

```html
<iframe id="support-admin" src="https://support.example.com/admin/support/tickets/"
        style="width:100%;border:0" title="Support administration"></iframe>
<script type="module">
  import { connectEscalatedFrame } from '@escalated-dev/escalated/embed'

  const frame = connectEscalatedFrame(document.getElementById('support-admin'), {
    origin: 'https://support.example.com',
    onNavigate: ({ route, title }) => highlightMenu(route),
  })
  frame.setTheme('light')
</script>
```

The frame sizes itself to its content and reports each page change; the
protocol is in the frontend guide.

### Session cookies in a frame

- **Same site** (`admin.example.com` framing `support.example.com`): Django's
  default `SESSION_COOKIE_SAMESITE = "Lax"` works.
- **Cross-site** (different registrable domains): the session and CSRF cookies
  must be sent in a third-party context, over HTTPS:

  ```python
  SESSION_COOKIE_SAMESITE = "None"
  SESSION_COOKIE_SECURE = True
  CSRF_COOKIE_SAMESITE = "None"  # also used for the XSRF-TOKEN cookie
  CSRF_COOKIE_SECURE = True
  ```

  Browsers that block third-party cookies will still not keep a session in a
  cross-site frame; use the Vue + Inertia or Django template setup there.
- CSRF protection is unchanged.

## The admin menu: `escalated.navigation`

While embedding is on, every Inertia page shares the admin menu, and
`escalated.embed.admin_navigation(user, request)` (or the
`{% escalated_admin_navigation %}` tag) returns the same list, embedding on or
off:

```json
[
  {
    "key": "tickets",
    "label": "Tickets",
    "route": "escalated.admin.tickets.index",
    "url": "/admin/support/tickets/",
    "icon": "tickets",
    "position": 20,
    "active": true,
    "badge": null,
    "plugin": null,
    "children": []
  }
]
```

It is filtered for the user: empty for anyone who fails Escalated's admin gate
(Django staff or superuser), unless you replaced it; screens whose feature is
off are left out (Roles while roles & permissions is off, API tokens while the
API is off, Plugins while plugins are off, Newsletters while they are off, the
knowledge base while it is switched off in the settings); and while roles &
permissions is on each item needs the permissions its URL requires. Plugin
admin menu items (`target`/`section` `admin`, filtered by their `permission`)
are included, sorted by `position` with the core items. `active` is true when
the request path is the item's URL or below it. Core `icon` keys match the
frontend's `escalatedNavIcons`.

## Security

- **The admin gate stays on by default.** Your `MIDDLEWARE` decorators run *in
  addition to* Escalated's own admin check (staff or superuser). Set
  `REPLACE_ADMIN_GATE` only if your decorators themselves restrict the views
  to admins: with it on, they are the only check on who reaches the admin
  (signed-in users your decorators let through are treated as admins on the
  embedded admin views only). Escalated refuses to start with
  `REPLACE_ADMIN_GATE` and no `MIDDLEWARE`. Two-factor and route permissions
  still apply either way, and the agent panel and `escalated.is_admin` keep
  Escalated's gates.
- **Framing is allow-listed.** In iframe mode only the origins you list (plus
  your own) may frame the admin; nothing else, and never `*`.
- **No open `postMessage`.** The frame talks only to an allow-listed parent
  origin and ignores messages from anywhere else.

## What does not move

The agent panel (`/support/agent/`), customer portal, guest pages, knowledge
base, widget, JSON API, SDK plugin endpoints and webhooks, inbound email, SSO,
attachment links, the two-factor enrolment screens and challenge (personal,
staff-wide pages, still at `/support/admin/settings/two-factor/` and
`/support/two-factor/challenge/`) and the newsletter admin
(`/support/admin/newsletters/`).

## Turning it off

Remove `EMBED` (or set `ESCALATED_EMBED=false`) and put
`path("support/", include("escalated.urls"))` back in your URLconf (with
embedding off, `escalated.embed_urls` serves exactly that too). The admin
returns to `/support/admin/` with Escalated's own chrome.

# Frontend integration

## Frontend Setup

Escalated uses Inertia.js with Vue 3. The frontend components are provided by the [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated) npm package.

### Tailwind Content

Add the Escalated package to your Tailwind `content` config so its classes aren't purged:

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### Page Resolver

Add the Escalated pages to your Inertia page resolver:

```javascript
// frontend/main.js
import { createApp, h } from 'vue'
import { createInertiaApp } from '@inertiajs/vue3'

createInertiaApp({
  resolve: name => {
    if (name.startsWith('Escalated/')) {
      const escalatedPages = import.meta.glob(
        '../node_modules/@escalated-dev/escalated/src/pages/**/*.vue',
        { eager: true }
      )
      const pageName = name.replace('Escalated/', '')
      return escalatedPages[`../node_modules/@escalated-dev/escalated/src/pages/${pageName}.vue`]
    }

    const pages = import.meta.glob('./pages/**/*.vue', { eager: true })
    return pages[`./pages/${name}.vue`]
  },
  setup({ el, App, props, plugin }) {
    createApp({ render: () => h(App, props) })
      .use(plugin)
      .mount(el)
  },
})
```

### CSRF

The shared pages send the CSRF token as `X-XSRF-TOKEN` (Inertia visits, from
an `XSRF-TOKEN` cookie) or `X-CSRF-TOKEN` (`fetch` calls such as the chat bar,
from a `csrf-token` meta tag). Django reads neither by default, so add
`EscalatedCsrfMiddleware` right after `CsrfViewMiddleware` and put the meta tag
in your `INERTIA_LAYOUT` template:

```python
MIDDLEWARE = [
    # ...
    "django.middleware.csrf.CsrfViewMiddleware",
    "escalated.middleware.EscalatedCsrfMiddleware",
    # ...
]
```

```html
<meta name="csrf-token" content="{{ csrf_token }}">
```

The middleware accepts either header in place of `X-CSRFToken` and sets the
`XSRF-TOKEN` cookie; a missing or wrong token is still refused. Setting
`CSRF_HEADER_NAME`/`CSRF_COOKIE_NAME` alone covers Inertia visits but not the
`fetch` calls.

### Named routes (`route()`)

The shared pages build their links with Ziggy's `route('escalated....', params)`.
Escalated shares its own route table as the `ziggy` Inertia prop on every
Escalated page, with the paths wherever you `include("escalated.urls")`, so
there is nothing to map by hand. Install the matching `route()` helper in your
`INERTIA_LAYOUT` template:

```html
{% load escalated_routes %}
{% escalated_route_helper %}  {# or {% escalated_route_helper nonce=request.csp_nonce %} #}
```

It does nothing if the page already has a `window.route` (e.g. ziggy-js), and
reads `window.Ziggy` before the prop. To change single names, set
`ESCALATED["ROUTES"]`: a path replaces a name and `None` removes it, e.g.
`{"login": "/accounts/login/"}` (`login` defaults to `settings.LOGIN_URL`). A
`ziggy` prop your own middleware shares is merged over Escalated's, name by name.

### Theming (Optional)

Register the `EscalatedPlugin` to render Escalated pages inside your app's layout — no page duplication needed:

```javascript
import { EscalatedPlugin } from '@escalated-dev/escalated'
import BaseLayout from '@/layouts/BaseLayout.vue'

createInertiaApp({
  setup({ el, App, props, plugin }) {
    createApp({ render: () => h(App, props) })
      .use(plugin)
      .use(EscalatedPlugin, {
        layout: BaseLayout,
        theme: {
          primary: '#3b82f6',
          radius: '0.75rem',
        }
      })
      .mount(el)
  },
})
```

Your layout component must accept a `#header` slot and a default slot. Escalated will render its sub-navigation in the header and page content in the default slot. Without the plugin, Escalated uses its own standalone layout.

See the [`@escalated-dev/escalated` README](https://github.com/escalated-dev/escalated) for full theming documentation and CSS custom properties.

## Translations (i18n)

Translations come from the central
[`escalated-locale`](https://github.com/escalated-dev/escalated-locale)
project, which publishes pre-compiled gettext artifacts at
`escalated_locale/locale/<lang>/LC_MESSAGES/django.{po,mo}` that plug
directly into Django's translation system via `LOCALE_PATHS`.

`pip install escalated-django` bundles a copy of those catalogues
(`escalated/_central_locale/`, synced from a tagged escalated-locale
release), so translations work with no extra install. To use the
standalone package instead, install the `locale` extra; when
`escalated_locale` is importable its catalogues win over the bundled copy:

```bash
pip install "escalated-django[locale]"
```

Wire the catalogues into your project's `settings.py`:

```python
# settings.py
from escalated.locale_paths import get_locale_paths

LOCALE_PATHS = get_locale_paths(
    # Optional: your project's own override directory (highest priority)
    BASE_DIR / "locale",
)
```

`LOCALE_PATHS` is searched in order, so the layering becomes:

1. Your project's `locale/` (if you passed one to `get_locale_paths`)
2. The plugin-local `escalated/locale/` override directory
3. The central baseline: the installed `escalated_locale/locale/` if
   present, otherwise the bundled `escalated/_central_locale/locale/`

Translation contributions should be sent to
[`escalated-locale`](https://github.com/escalated-dev/escalated-locale).
The plugin-local `escalated/locale/` directory is reserved for
Django-specific overrides that shouldn't ship to other framework
plugins.

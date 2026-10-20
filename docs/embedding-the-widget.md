# Embedding the widget on other sites

The support widget, ticket form and live chat can run on a site other than
the one Escalated is installed on: a store, a marketing site or a customer
portal loads one script from your Escalated install. Nothing changes until you
list the sites that may do this.

## 1. Allow the embedding sites

Either in your Django settings:

```python
ESCALATED = {
    # ...
    "WIDGET_ALLOWED_ORIGINS": ["https://shop.example.com", "https://*.example.org"],
}
```

(a comma-separated string works too, which makes reading it from the
environment easy:
`os.environ.get("ESCALATED_WIDGET_ALLOWED_ORIGINS", "")`), or in the admin
settings as `widget_allowed_origins` (one per line). Both lists are combined.
Each entry is an origin: `scheme://host[:port]`, no path. `https://*.example.org`
matches every subdomain of `example.org` but not `example.org` itself. A bare
`*` is rejected, and the admin settings refuse to save a list with an invalid
entry.

The widget's switches apply to embedded requests unchanged:

- `widget_enabled` turns the whole widget on. It is off on a new install;
  installs that already existed keep it on (migration `0031`).
- `chat_enabled` turns on live chat in the widget (start, messages, typing,
  end, rate; availability reports `available: false` while it is off). Off on a
  new install; existing installs keep it on.
- `guest_tickets_enabled` and `widget_ticket_creation_enabled` must both be on
  for the widget to create tickets.
- `knowledge_base_enabled` and `knowledge_base_public` apply to the widget's
  article search and articles (`404` when the knowledge base is off, `403` when
  it is not public and the visitor is not signed in; a cross-origin visitor is
  always a guest).

All of them, plus `widget_color`, `widget_position`, `widget_greeting` and
`widget_departments`, are saved from the admin Settings page.

## 2. Add the script to the other site

```html
<script src="https://help.example.com/support/widget/embed.js" async></script>
```

For an on-page support form instead of a floating button:

```html
<div id="support-form"></div>
<script
    src="https://help.example.com/support/widget/embed.js"
    data-mode="inline"
    data-target="#support-form"
    data-tabs="ticket"
    data-meta-order-number="A-1001"
></script>
```

All host parameters (tabs, prefill, metadata, title, the JavaScript API) are
described in the frontend package's
[embedding guide](https://github.com/escalated-dev/escalated/blob/main/docs/embedding-the-widget.md).

## What the server does

For a request whose `Origin` is on the list, every widget route under
`{ROUTE_PREFIX}/widget/` (chat routes included):

- answers preflight requests (`OPTIONS` with `Access-Control-Request-Method`)
  with `204`, the allowed methods (`GET, POST, OPTIONS`) and headers
  (`Accept, Authorization, Content-Type, X-Requested-With`);
- adds `Access-Control-Allow-Origin`, `Access-Control-Expose-Headers:
  Retry-After` and `Vary: Origin` to every response, including validation
  errors (400/422), disabled-widget answers (403), not-found (404) and
  rate-limit answers (429). It never sends `Access-Control-Allow-Credentials`;
- treats the visitor as a guest (`request.user` is `AnonymousUser`) even if
  the same browser is signed in to Escalated. A signed-in agent's session is
  never used from another site.

Only those requests skip Django's CSRF check: they carry no session cookie
and run as a guest, so there is no token to send and nothing to protect.
Requests from any other origin, and same-origin requests, go through the
host's `CsrfViewMiddleware` like any other view (a same-origin page sends its
token as `X-CSRF-TOKEN`, so set `CSRF_HEADER_NAME = "HTTP_X_CSRF_TOKEN"` or
embed from a listed origin) and get no CORS headers. A preflight from an origin
that is not listed gets `204` with no `Access-Control-Allow-Origin`, so the
browser blocks the request.

### Host parameters

`/config/` returns `accepts_metadata: true`. Widget tickets store the
`metadata` object the page sends in `Ticket.metadata`; live chats store it in
`Ticket.chat_metadata` and `ChatSession.metadata`. The values come from the
visitor's browser, so only a flat map is kept: up to 25 entries, keys of
letters, digits, `_ . : -` (64 characters at most), and string, number or
boolean values (strings trimmed and cut to 500 characters; arrays, objects and
null are dropped). `page_url` is kept only when it is an http(s) URL of at most
2048 characters. `embedded_on` is always set by the server from the request's
`Origin` and cannot be supplied by the page. A `metadata` that is not an
object, or has more than 50 keys, is rejected with `400`. Treat all of it as
unverified visitor input.

### The widget's API

The shared widget calls these paths under `{ROUTE_PREFIX}/widget` (no trailing
slash, so POSTs never meet an `APPEND_SLASH` redirect). The original
trailing-slash routes and their answer shapes are unchanged.

| Method + path | Answer |
|---|---|
| `GET /config` | `color`, `greeting`, `position` (admin setting `widget_position`, default `bottom-right`), `departments` (active, `[{id, name}]`), `kb_enabled`, `guest_tickets_enabled`, `accepts_metadata`, `status_lookup_enabled: false`, plus the original `widget_*` keys. A disabled widget answers `403` with `enabled: false`. |
| `GET /chat/availability` | `{available}`; optional `department_id` |
| `GET /articles?q=` | `{articles: [{title, slug, excerpt}]}` |
| `GET /articles/<slug>` | the published article's `title`, `slug`, `body`, `category` at the top level |
| `POST /tickets` | `201 {message, reference, guest_access_token}`; takes `name`, `email`, `subject`, `description`, optional `department_id` and `metadata` |
| `POST /chat/start` | `201 {id, session_id, status, messages, agent}`; takes `name`, `email`, optional `department_id`, `message`, `subject`, `metadata` |
| `GET /chat/<id>/messages` | `{messages: [{id, body, is_agent, author: {name}, created_at}], agent, typing, ended}` |
| `POST /chat/<id>/messages` | `{body}` from the guest |
| `POST /chat/<id>/typing`, `/end`, `/rate` | typing signal, end the chat, rate an ended chat (`{rating: 1-5, comment?}`) |

`id` is the chat's random session token (256 bits); every chat path needs it,
and an unknown token gets `404`. Validation errors on these paths are `422`
with `{message, errors: {field: [messages]}}`; an unknown or inactive
`department_id` is a validation error.

There is no ticket status lookup by email: a claimed address never unlocks a
ticket, so `/config` sends `status_lookup_enabled: false` and the widget hides
its Status tab. The old `widget/tickets/lookup/?reference=&email=` route has
been removed for the same reason. Guests follow their ticket through the link
in their confirmation email.

### The script

`GET {ROUTE_PREFIX}/widget/embed.js` serves the bundle shipped in
`escalated/static/escalated/widget/escalated-widget.js`, vendored from
`@escalated-dev/escalated`, with a one-hour cache and an ETag (`304` on
`If-None-Match`). Set `ESCALATED["WIDGET_SERVE_SCRIPT"] = False` to unmount the
route, for example when you serve the bundle from a CDN or through
`collectstatic`. Pages then need `data-base-url`.

## Configuration

```python
ESCALATED = {
    "WIDGET_ALLOWED_ORIGINS": [],  # list or comma-separated string
    "WIDGET_PREFLIGHT_MAX_AGE": 600,  # seconds browsers may cache a preflight
    "WIDGET_SERVE_SCRIPT": True,  # mount {ROUTE_PREFIX}/widget/embed.js
}
```

## Troubleshooting

- **The browser reports a CORS error.** The page's origin is not on the list,
  or it differs in scheme or port (`http://` vs `https://`, `:8080`).
- **Same-origin requests look cross-origin behind a proxy.** The server
  compares `Origin` with `request.scheme` and `request.get_host()`. Behind a
  TLS-terminating proxy, set `SECURE_PROXY_SSL_HEADER` (and
  `USE_X_FORWARDED_HOST` if the proxy rewrites the host) so Django sees the
  public scheme and host.
- **django-cors-headers.** It is not needed for the widget routes. If its
  `CORS_URLS_REGEX` covers `/support/widget/`, its middleware answers those
  preflights first with its own settings.

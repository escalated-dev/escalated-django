# Verified guest access

Guest ticket creation, widget live chat and ticket lookup require proof that the
guest can read the mailbox they give. This is the same contract as
escalated-laravel's `docs/guest-access.md`, and the shared frontend
(`@escalated-dev/escalated` 0.12.3 or later) already implements the client side:
`Guest/Create` asks for a code and offers a lookup, and the widget does the same
when `/widget/config` says `guest_verification_required: true`.

## Upgrade notes

Run `python manage.py migrate escalated` (migration `0032` adds the
`guest_verifications` table and four nullable ticket columns).

Configure working outbound mail (`EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`): the
code is only ever sent by email. Use a shared cache (Redis, Memcached or the
database cache) for `GUEST_RATE_LIMIT["CACHE"]` when you run several workers,
so the delivery budgets below are counted once. Keep `SECRET_KEY` the same on
every worker: it signs grants and keys the stored email and code digests.
Rotating it revokes every grant and outstanding code.

**Existing guest links stop working.** Tickets created before this release
were opened by a permanent 64-character `guest_token` in the URL
(`guest/<token>/`), returned by the widget as `guest_token` /
`guest_access_token`. Those tokens no longer authorize anything. The tickets
themselves are unchanged. A guest gets a new link by verifying their email
and entering the ticket reference in the lookup form (browser `Guest/Create`
page or the widget's Status tab); the lookup issues a grant and clears the old
token. Inbound email and agent-created tickets are not treated as proof.

If you need the old links to keep working for a transition period, set:

```python
ESCALATED = {
    "GUEST_ACCESS": {"LEGACY_TOKENS": True},
}
```

That re-opens the security gap (a forwarded link is a permanent key to the
conversation), so turn it off again once your guests have renewed.

Browser `verification` and `lookup` keep Django's CSRF protection. The shared
pages send the token as `X-XSRF-TOKEN` (from an `XSRF-TOKEN` cookie) or
`X-CSRF-TOKEN` (from a `csrf-token` meta tag), which Django does not read by
default: add `escalated.middleware.EscalatedCsrfMiddleware` after
`CsrfViewMiddleware` (see the README's CSRF section). Widget
requests follow the widget's CORS/CSRF rules (see
[embedding the widget](embedding-the-widget.md)); the mobile endpoints are
exempt, since they act on the emailed code only.

Older clients that do not send a code can no longer create guest tickets or
start chats.

## Settings

```python
ESCALATED = {
    "GUEST_ACCESS": {
        "TTL_MINUTES": 1440,  # grant lifetime, clamped to 5..10080
        "CHALLENGES_PER_CLIENT_PER_HOUR": 3,  # codes per mailbox per client IP
        "CHALLENGES_PER_MAILBOX_PER_HOUR": 10,  # codes per mailbox across all IPs
        "LEGACY_TOKENS": False,
    },
}
```

`python manage.py purge_expired_data` also removes expired codes.

## Email proof

Each surface exposes `POST verification` and `POST lookup`:

| Surface | Prefix |
| --- | --- |
| Browser | `<ROUTE_PREFIX>/guest/` |
| Widget | `<ROUTE_PREFIX>/widget/` |
| Mobile (when `API_ENABLED`) | `<API_PREFIX>/mobile/guest/` |

Request a code with `{"email": "recipient@example.com", "purpose": "ticket"}`;
the other purposes are `chat` and `lookup`. The answer is `202` with
`verification_id`, `expires_in: 600` and a generic message. Only the email
contains the eight-digit code. `ticket` and `lookup` codes need guest tickets
enabled; `chat` codes need `chat_enabled`. The widget prefix also needs the
widget enabled.

Send `verification_id` and `verification_code` with the operation the code was
for. A code is bound to the normalized email and the purpose, expires after ten
minutes, allows at most five guesses and can be used once. Using it and the
operation it authorizes (creating the ticket and its attachments, starting the
chat, issuing lookup grants) commit in one transaction; wrong guesses stay
counted, and a failed operation leaves the code usable.

Code delivery for one mailbox is limited to 3 per hour from one client IP and
10 per hour across all IPs (`429` with `Retry-After`), so one client cannot
lock the mailbox owner out and nobody can flood the mailbox. The existing
per-IP guest submission limit (`GUEST_RATE_LIMIT`) also applies.

The database stores neither the code nor the address in the clear: both are
kept as `SECRET_KEY`-keyed HMAC digests.

## Tickets and grants

- Browser: `guest/store/` takes `guest_name`, `guest_email` (or `name`,
  `email`) plus the proof fields and redirects to `guest/<grant>/`.
- Widget: `POST widget/tickets` returns `guest_access_token` and `expires_at`
  (the older `widget/tickets/create/` returns the grant as `ticket.guest_token`
  with `ticket.expires_at`).
- Widget status: `GET widget/tickets/<reference>` with
  `Authorization: Bearer <grant>`; the grant must belong to that reference. An
  email query parameter authorizes nothing.

The grant is an opaque signed token: do not parse it or assume a length. It
expires after `TTL_MINUTES` (default 24 hours). The ticket stores only the
SHA-256 hash of the grant's random nonce, so issuing a new grant (a lookup)
revokes the old one and every attachment link issued under it. Changing the
ticket's `guest_email` also revokes access. Trusted host code can call
`escalated.guest_access.revoke(ticket)`.

The guest page shows public replies only, without ticket or reply `metadata`,
the requester record or agent email addresses. Guest answers are sent with
`Cache-Control: no-store` and `Referrer-Policy: no-referrer`. Redact
`guest/<grant>/` path segments and `Authorization` headers from access logs.

## Lookup and renewal

After requesting a `lookup` code, `POST lookup` with `email`, `reference`,
`verification_id` and `verification_code`. The answer is `{"data": [...]}`;
each match has `reference`, `subject`, `guest_access_token` and `expires_at`
(at most 20). A reference alone unlocks nothing: the ticket's guest email must
match the proven address. The result may be empty, and the code is used either
way.

## Not covered yet

- Live-chat session tokens (`chat/<token>/...`) are still the per-session
  random token from `chat/start`; they do not expire with a grant.
- There are no mobile guest ticket routes (create, read, reply) in this
  package, only mobile `verification` and `lookup`; the grants they return open
  the browser guest page.
- Lookup matches the Escalated reference only; there is no
  `external_reference` column yet.

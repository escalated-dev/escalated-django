<p align="center">
  <a href="README.ar.md">العربية</a> •
  <a href="README.de.md">Deutsch</a> •
  <a href="../../README.md">English</a> •
  <a href="README.es.md">Español</a> •
  <a href="README.fr.md">Français</a> •
  <a href="README.it.md">Italiano</a> •
  <a href="README.ja.md">日本語</a> •
  <a href="README.ko.md">한국어</a> •
  <a href="README.nl.md">Nederlands</a> •
  <b>Polski</b> •
  <a href="README.pt-BR.md">Português (BR)</a> •
  <a href="README.ru.md">Русский</a> •
  <a href="README.tr.md">Türkçe</a> •
  <a href="README.zh-CN.md">简体中文</a>
</p>

# Escalated for Django

[![Tests](https://github.com/escalated-dev/escalated-django/actions/workflows/run-tests.yml/badge.svg)](https://github.com/escalated-dev/escalated-django/actions/workflows/run-tests.yml)
[![FOSSA Status](https://app.fossa.com/api/projects/custom%2B62107%2Fgithub.com%2Fescalated-dev%2Fescalated-django.svg?type=shield)](https://app.fossa.com/projects/custom%2B62107%2Fgithub.com%2Fescalated-dev%2Fescalated-django?ref=badge_shield)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2+-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

W pełni funkcjonalny, wbudowywalny system zgłoszeń wsparcia dla Django. Dodaj go do dowolnej aplikacji — otrzymasz kompletny helpdesk ze śledzeniem SLA, regułami eskalacji, przepływami pracy agentów i portalem klienta. Nie wymaga zewnętrznych usług.

> **[escalated.dev](https://escalated.dev)** — Dowiedz się więcej, zobacz dema i porównaj opcje Cloud z Self-Hosted.

**Trzy tryby hostingu.** Uruchom w pełni na własnym serwerze, synchronizuj z centralną chmurą dla widoczności wielu aplikacji lub przekieruj wszystko do chmury. Zmień tryb jedną zmianą konfiguracji.

## Funkcje

- **Cykl życia zgłoszenia** — Tworzenie, przypisywanie, odpowiadanie, rozwiązywanie, zamykanie, ponowne otwieranie z konfigurowalnymi przejściami statusów
- **Silnik SLA** — Cele odpowiedzi i rozwiązania według priorytetu, obliczanie godzin pracy, automatyczne wykrywanie naruszeń
- **Reguły eskalacji** — Reguły warunkowe automatycznie eskalujące, zmieniające priorytet, ponownie przypisujące lub powiadamiające
- **Panel agenta** — Kolejka zgłoszeń z filtrami, akcjami zbiorczymi, notatkami wewnętrznymi, szablonowymi odpowiedziami
- **Portal klienta** — Samoobsługowe tworzenie zgłoszeń, odpowiedzi i śledzenie statusu
- **Panel administracyjny** — Zarządzanie działami, politykami SLA, regułami eskalacji, tagami i przeglądanie raportów
- **Załączniki plików** — Przesyłanie metodą przeciągnij i upuść z konfigurowalnym magazynem i limitami rozmiaru
- **Oś czasu aktywności** — Pełny dziennik audytu każdej akcji na każdym zgłoszeniu
- **Powiadomienia email** — Konfigurowalne powiadomienia per zdarzenie z obsługą webhooków
- **Routing departamentowy** — Organizacja agentów w działy z automatycznym przypisywaniem (round-robin)
- **System tagów** — Kategoryzacja zgłoszeń kolorowymi tagami
- **Inertia.js + Vue 3 UI** — Współdzielony frontend przez [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)
- **Dzielenie zgłoszeń** — Rozdzielenie odpowiedzi na nowe niezależne zgłoszenie z zachowaniem oryginalnego kontekstu
- **Ticket snooze** — Odraczanie zgłoszeń z predefiniowanymi ustawieniami (1h, 4h, jutro, przyszły tydzień); komenda `python manage.py wake_snoozed_tickets` budzi je automatycznie według harmonogramu
- **Zapisane widoki / niestandardowe kolejki** — Zapisywanie, nazywanie i udostępnianie presetów filtrów jako wielokrotnie używalnych widoków zgłoszeń
- **Osadzalny widżet wsparcia** — Lekki widżet `<script>` z wyszukiwaniem KB, formularzem zgłoszeń i sprawdzaniem statusu
- **Wątkowanie e-mail** — Wychodzące wiadomości zawierają poprawne nagłówki `In-Reply-To` i `References` dla prawidłowego wątkowania w klientach poczty
- **Szablony e-mail z marką** — Konfigurowalne logo, kolor główny i tekst stopki dla wszystkich wychodzących wiadomości
- **Real-time broadcasting** — Opcjonalne nadawanie przez Django Channels z automatycznym fallbackiem na polling
- **Przełącznik bazy wiedzy** — Włączenie lub wyłączenie publicznej bazy wiedzy z ustawień administracyjnych

## Wymagania

- Python 3.10+
- Django 4.2+
- Node.js 18+ (dla zasobów frontendowych)

## Szybki Start

```bash
pip install escalated-django
npm install @escalated-dev/escalated
```

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    'django.contrib.contenttypes',
    'inertia',
    'escalated',
]
```

### 2. Include URLs

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path("support/", include("escalated.urls")),
]
```

### 3. Run migrations

```bash
python manage.py migrate escalated
```

Visit `/support` — you're live.

## Konfiguracja Frontend

Escalated używa Inertia.js z Vue 3. Komponenty frontendowe są dostarczane przez pakiet npm [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated).

### Zawartość Tailwind

Dodaj pakiet Escalated do konfiguracji `content` Tailwind, aby jego klasy nie zostały usunięte:

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### Resolver Stron

Dodaj strony Escalated do resolvera stron Inertia:

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

### Motywy (Opcjonalnie)

Zarejestruj `EscalatedPlugin`, aby renderować strony Escalated wewnątrz layoutu twojej aplikacji — nie jest potrzebna duplikacja stron:

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

Zobacz [README `@escalated-dev/escalated`](https://github.com/escalated-dev/escalated) po pełną dokumentację motywów i właściwości CSS.

## Tryby Hostingu

### Self-Hosted (domyślny)

Wszystko pozostaje w Twojej bazie danych. Brak zewnętrznych wywołań. Pełna autonomia.

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### Zsynchronizowany

Lokalna baza danych + automatyczna synchronizacja z `cloud.escalated.dev` dla zunifikowanej skrzynki odbiorczej w wielu aplikacjach. Jeśli chmura jest nieosiągalna, Twoja aplikacja nadal działa — zdarzenia są kolejkowane i ponawiane.

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

### Chmura

Wszystkie dane zgłoszeń są przekazywane przez API chmury. Twoja aplikacja obsługuje autoryzację i renderuje interfejs, ale dane są przechowywane w chmurze.

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

Wszystkie trzy tryby współdzielą te same widoki, interfejs i logikę biznesową. Wzorzec sterownika obsługuje resztę.

## Konfiguracja

Add to your `settings.py`:

```python
ESCALATED = {
    "MODE": "self_hosted",              # self_hosted | synced | cloud
    "TABLE_PREFIX": "escalated_",
    "ROUTE_PREFIX": "support",
    "DEFAULT_PRIORITY": "medium",

    # Tickets
    "ALLOW_CUSTOMER_CLOSE": True,
    "AUTO_CLOSE_RESOLVED_AFTER_DAYS": 7,
    "MAX_ATTACHMENTS": 5,
    "MAX_ATTACHMENT_SIZE_KB": 10240,

    # SLA
    "SLA": {
        "ENABLED": True,
        "BUSINESS_HOURS_ONLY": False,
        "BUSINESS_HOURS": {
            "START": "09:00",
            "END": "17:00",
            "TIMEZONE": "UTC",
            "DAYS": [1, 2, 3, 4, 5],
        },
    },

    # Notifications
    "NOTIFICATION_CHANNELS": ["email"],
    "WEBHOOK_URL": None,

    # Cloud/Synced mode
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": None,
}
```

## Komendy Zarządzania

```bash
# Check SLA deadlines and fire breach notifications
python manage.py check_sla

# Evaluate escalation rules against open tickets
python manage.py evaluate_escalations

# Auto-close tickets resolved more than N days ago
python manage.py close_resolved --days 7

# Purge old activity logs
python manage.py purge_activities --days 90
```

Schedule these with cron, Celery Beat, or django-crontab for automated enforcement.

## Trasy

All routes use the configurable prefix (default: `support`).

| Route | Method | Description |
|-------|--------|-------------|
| `/support/tickets/` | GET | Customer ticket list |
| `/support/tickets/create/` | GET | New ticket form |
| `/support/tickets/<id>/` | GET | Ticket detail |
| `/support/agent/` | GET | Agent dashboard |
| `/support/agent/tickets/` | GET | Agent ticket queue |
| `/support/agent/tickets/<id>/` | GET | Agent ticket view |
| `/support/admin/reports/` | GET | Admin reports |
| `/support/admin/departments/` | GET | Department management |
| `/support/admin/sla-policies/` | GET | SLA policy management |
| `/support/admin/escalation-rules/` | GET | Escalation rule management |
| `/support/admin/tags/` | GET | Tag management |
| `/support/admin/canned-responses/` | GET | Canned response management |
| `/support/agent/tickets/bulk/` | POST | Bulk actions on multiple tickets |
| `/support/agent/tickets/<id>/follow/` | POST | Follow/unfollow a ticket |
| `/support/agent/tickets/<id>/macro/` | POST | Apply a macro to a ticket |
| `/support/agent/tickets/<id>/presence/` | POST | Update presence on a ticket |
| `/support/agent/tickets/<id>/pin/<reply_id>/` | POST | Pin/unpin an internal note |
| `/support/tickets/<id>/rate/` | POST | Submit satisfaction rating |

## Sygnały

Connect to ticket lifecycle events:

```python
from escalated.signals import ticket_created, ticket_resolved

@receiver(ticket_created)
def on_ticket_created(sender, ticket, user, **kwargs):
    print(f"New ticket: {ticket.reference}")

@receiver(ticket_resolved)
def on_ticket_resolved(sender, ticket, user, **kwargs):
    print(f"Resolved: {ticket.reference}")
```

Available signals: `ticket_created`, `ticket_updated`, `ticket_status_changed`, `ticket_assigned`, `ticket_unassigned`, `ticket_priority_changed`, `ticket_escalated`, `ticket_resolved`, `ticket_closed`, `ticket_reopened`, `reply_created`, `internal_note_added`, `sla_breached`, `sla_warning`, `tag_added`, `tag_removed`, `department_changed`.

## SDK Wtyczek

Escalated obsługuje wtyczki niezależne od frameworka zbudowane z [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk). Wtyczki są pisane raz w TypeScript i działają na wszystkich backendach Escalated.

### Wymagania

- Node.js 20+
- `@escalated-dev/plugin-runtime` installed in your project

### Instalacja Wtyczek

```bash
npm install @escalated-dev/plugin-runtime
npm install @escalated-dev/plugin-slack
npm install @escalated-dev/plugin-jira
```

### Włączanie Wtyczek SDK

```python
# settings.py
ESCALATED = {
    # ... existing config ...
    "SDK_ENABLED": True,
}
```

### Jak To Działa

SDK plugins run as a long-lived Node.js subprocess managed by `@escalated-dev/plugin-runtime`, communicating with Django over JSON-RPC 2.0 via stdio. Every ticket lifecycle signal is dual-dispatched — first to Django signal handlers, then forwarded to the plugin runtime.

### Tworzenie Własnej Wtyczki

```typescript
import { definePlugin } from '@escalated-dev/plugin-sdk'

export default definePlugin({
  name: 'my-plugin',
  version: '1.0.0',
  actions: {
    'ticket.created': async (event, ctx) => {
      ctx.log.info('New ticket!', event)
    },
  },
})
```

### Zasoby

- [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) — TypeScript SDK do tworzenia wtyczek
- [Plugin Runtime](https://github.com/escalated-dev/escalated-plugin-runtime) — Host runtime dla wtyczek
- [Plugin Development Guide](https://github.com/escalated-dev/escalated-docs) — Pełna dokumentacja

See the detailed [SDK Plugin Bridge](#sdk-plugin-bridge) section below for the full architecture, supported `ctx.*` callbacks, hook event mapping, and resilience documentation.

## Most Wtyczek SDK

The Plugin Bridge connects your Django app to the Node.js
`@escalated-dev/plugin-runtime` process via JSON-RPC 2.0 over stdio.
It enables SDK plugins — JavaScript/TypeScript packages that hook into
ticket lifecycle events, expose custom API endpoints, and persist data
through the host ORM — without requiring any Node.js code in your Django
project.

### How it works

1. On startup Django spawns `node @escalated-dev/plugin-runtime` as a
   long-lived subprocess.
2. A protocol handshake is performed and plugin manifests are exchanged.
3. URL patterns for plugin pages, API endpoints, and webhooks are
   dynamically registered.
4. Every ticket lifecycle signal (created, replied, resolved, etc.) is
   dual-dispatched — first to the standard Django signal handlers and then
   to the bridge, which forwards the event to the runtime.
5. Plugin code can call back into Django via `ctx.*` methods
   (`ctx.tickets.find`, `ctx.store.set`, `ctx.config.get`, etc.) over the
   same bidirectional JSON-RPC channel.

### Wymagania

- Node.js 18+
- `@escalated-dev/plugin-runtime` installed in your project's
  `node_modules`

### Szybki start

**1. Install the runtime**

```bash
npm install @escalated-dev/plugin-runtime
```

**2. Enable the bridge in settings**

```python
ESCALATED = {
    # ... existing config ...

    # SDK plugin bridge
    "SDK_ENABLED": True,

    # Optional overrides (defaults shown):
    # "RUNTIME_COMMAND": "node node_modules/@escalated-dev/plugin-runtime/dist/index.js",
    # "RUNTIME_CWD": BASE_DIR,  # working directory for the Node subprocess
}
```

**3. Run the migration**

```bash
python manage.py migrate escalated
```

This creates the `escalated_plugin_store` table used by `ctx.store.*` and
`ctx.config.*` callbacks.

### Routes registered by the bridge

Plugin manifests can declare three types of routes.  All are automatically
registered under the configured `ROUTE_PREFIX` (default `support`):

| Category | URL pattern | Auth |
|----------|-------------|------|
| Pages | `/{prefix}/admin/plugins/{plugin}/{route}` | Admin required |
| Endpoints | `/{prefix}/api/plugins/{plugin}/{path}` | Admin required |
| Webhooks | `/{prefix}/webhooks/plugins/{plugin}/{path}` | None (public) |

### Supported `ctx.*` callbacks

| Method | Description |
|--------|-------------|
| `ctx.config.all` / `ctx.config.get` / `ctx.config.set` | Per-plugin config blob |
| `ctx.store.get` / `ctx.store.set` / `ctx.store.query` / `ctx.store.insert` / `ctx.store.update` / `ctx.store.delete` | Per-plugin key/value store |
| `ctx.tickets.find` / `ctx.tickets.query` / `ctx.tickets.create` / `ctx.tickets.update` | Ticket ORM access |
| `ctx.replies.find` / `ctx.replies.query` / `ctx.replies.create` | Reply ORM access |
| `ctx.contacts.find` / `ctx.contacts.findByEmail` / `ctx.contacts.create` | User model access |
| `ctx.tags.all` / `ctx.tags.create` | Tag access |
| `ctx.departments.all` / `ctx.departments.find` | Department access |
| `ctx.agents.all` / `ctx.agents.find` | Agent (user) access |
| `ctx.broadcast.toChannel` / `ctx.broadcast.toUser` / `ctx.broadcast.toTicket` | Django Channels broadcast (optional) |
| `ctx.emit` | Fire another action hook from inside a plugin |
| `ctx.log` | Log to Django's logger |

### Hook events dispatched to the bridge

Every ticket signal fires a corresponding SDK hook:

| Django signal | SDK hook |
|---------------|----------|
| `ticket_created` | `ticket.created` |
| `ticket_updated` | `ticket.updated` |
| `ticket_status_changed` | `ticket.status_changed` |
| `ticket_assigned` | `ticket.assigned` |
| `ticket_priority_changed` | `ticket.priority_changed` |
| `ticket_resolved` | `ticket.resolved` |
| `ticket_closed` | `ticket.closed` |
| `ticket_escalated` | `ticket.escalated` |
| `reply_created` | `reply.created` |
| `sla_breached` | `sla.breached` |

### Odporność

- The bridge is spawned **lazily** on first use — health-check requests are
  never slowed down.
- If the Node.js runtime crashes it is automatically restarted with
  **exponential backoff** (up to 5 minutes between attempts).
- Action hooks degrade gracefully (drop with a warning) when the runtime is
  unavailable.  Filter hooks return the unmodified value.
- The action queue is capped at 1 000 in-flight entries to prevent memory
  growth.

## Dostępne Również Dla

- **[Escalated for Laravel](https://github.com/escalated-dev/escalated-laravel)** — Pakiet Laravel Composer
- **[Escalated for Rails](https://github.com/escalated-dev/escalated-rails)** — Silnik Ruby on Rails
- **[Escalated for Django](https://github.com/escalated-dev/escalated-django)** — Aplikacja wielokrotnego użytku Django (jesteś tutaj)
- **[Escalated for AdonisJS](https://github.com/escalated-dev/escalated-adonis)** — Pakiet AdonisJS v6
- **[Escalated for Filament](https://github.com/escalated-dev/escalated-filament)** — Wtyczka panelu administracyjnego Filament v3
- **[Shared Frontend](https://github.com/escalated-dev/escalated)** — Komponenty UI Vue 3 + Inertia.js

Ta sama architektura, ten sam interfejs Vue, te same trzy tryby hostingu — dla każdego ważnego frameworka backendowego.

## Rozwój

```bash
pip install -e ".[dev]"
pytest
```

## Licencja

MIT

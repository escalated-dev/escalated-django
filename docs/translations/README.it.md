<p align="center">
  <a href="README.ar.md">العربية</a> •
  <a href="README.de.md">Deutsch</a> •
  <a href="../../README.md">English</a> •
  <a href="README.es.md">Español</a> •
  <a href="README.fr.md">Français</a> •
  <b>Italiano</b> •
  <a href="README.ja.md">日本語</a> •
  <a href="README.ko.md">한국어</a> •
  <a href="README.nl.md">Nederlands</a> •
  <a href="README.pl.md">Polski</a> •
  <a href="README.pt-BR.md">Português (BR)</a> •
  <a href="README.ru.md">Русский</a> •
  <a href="README.tr.md">Türkçe</a> •
  <a href="README.zh-CN.md">简体中文</a>
</p>

# Escalated for Django

[![Tests](https://github.com/escalated-dev/escalated-django/actions/workflows/run-tests.yml/badge.svg)](https://github.com/escalated-dev/escalated-django/actions/workflows/run-tests.yml)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2+-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Un sistema di ticket di supporto completo e integrabile per Django. Aggiungilo a qualsiasi app — ottieni un helpdesk completo con tracciamento SLA, regole di escalation, flussi di lavoro degli agenti e un portale clienti. Nessun servizio esterno richiesto.

> **[escalated.dev](https://escalated.dev)** — Scopri di più, guarda le demo e confronta le opzioni Cloud vs Self-Hosted.

**Tre modalità di hosting.** Esecuzione completamente self-hosted, sincronizzazione con un cloud centrale per la visibilità multi-app, o proxy di tutto verso il cloud. Cambio modalità con una singola modifica alla configurazione.

## Funzionalità

- **Ciclo di vita del ticket** — Creare, assegnare, rispondere, risolvere, chiudere, riaprire con transizioni di stato configurabili
- **Motore SLA** — Obiettivi di risposta e risoluzione per priorità, calcolo delle ore lavorative, rilevamento automatico delle violazioni
- **Regole di escalation** — Regole basate su condizioni che escalano, ripriorizzano, riassegnano o notificano automaticamente
- **Dashboard dell'agente** — Coda ticket con filtri, azioni di massa, note interne, risposte predefinite
- **Portale clienti** — Creazione ticket self-service, risposte e tracciamento dello stato
- **Pannello di amministrazione** — Gestire reparti, policy SLA, regole di escalation, tag e visualizzare report
- **Allegati** — Upload drag-and-drop con archiviazione configurabile e limiti di dimensione
- **Timeline delle attività** — Log di audit completo di ogni azione su ogni ticket
- **Notifiche email** — Notifiche configurabili per evento con supporto webhook
- **Routing per reparto** — Organizzare gli agenti in reparti con assegnazione automatica (round-robin)
- **Sistema di tagging** — Categorizzare i ticket con tag colorati
- **Inertia.js + Vue 3 UI** — Frontend condiviso tramite [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)
- **Divisione ticket** — Dividere una risposta in un nuovo ticket autonomo preservando il contesto originale
- **Ticket snooze** — Sospendi i ticket con preimpostazioni (1h, 4h, domani, prossima settimana); il comando `python manage.py wake_snoozed_tickets` li riattiva automaticamente
- **Viste salvate / code personalizzate** — Salvare, denominare e condividere preset di filtri come viste ticket riutilizzabili
- **Widget di supporto integrabile** — Widget leggero `<script>` con ricerca KB, modulo ticket e verifica stato
- **Threading email** — Le email in uscita includono gli header `In-Reply-To` e `References` per un threading corretto nei client di posta
- **Template email personalizzati** — Logo, colore primario e testo del footer configurabili per tutte le email in uscita
- **Real-time broadcasting** — Broadcasting opzionale tramite Django Channels con fallback automatico al polling
- **Toggle base di conoscenza** — Abilitare o disabilitare la base di conoscenza pubblica dalle impostazioni admin

## Requisiti

- Python 3.10+
- Django 4.2+
- Node.js 18+ (per le risorse frontend)

## Avvio Rapido

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

## Configurazione Frontend

Escalated utilizza Inertia.js con Vue 3. I componenti frontend sono forniti dal pacchetto npm [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated).

### Contenuto Tailwind

Aggiungi il pacchetto Escalated alla configurazione `content` di Tailwind affinché le sue classi non vengano rimosse:

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### Risolutore di Pagine

Aggiungi le pagine Escalated al tuo resolver delle pagine Inertia:

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

### Temi (Opzionale)

Registra l'`EscalatedPlugin` per renderizzare le pagine Escalated all'interno del layout della tua app — nessuna duplicazione di pagine necessaria:

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

Consulta il [README di `@escalated-dev/escalated`](https://github.com/escalated-dev/escalated) per la documentazione completa sui temi e le proprietà CSS personalizzate.

## Modalità di Hosting

### Self-Hosted (predefinito)

Tutto rimane nel tuo database. Nessuna chiamata esterna. Piena autonomia.

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### Sincronizzato

Database locale + sincronizzazione automatica con `cloud.escalated.dev` per una casella di posta unificata su più app. Se il cloud non è raggiungibile, la tua app continua a funzionare — gli eventi vengono messi in coda e riprovati.

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

### Cloud

Tutti i dati dei ticket vengono inviati all'API cloud. La tua app gestisce l'autenticazione e renderizza l'interfaccia, ma l'archiviazione risiede nel cloud.

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

Tutte e tre le modalità condividono le stesse view, l'interfaccia e la logica di business. Il pattern driver gestisce il resto.

## Configurazione

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

## Comandi di Gestione

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

## Percorsi

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

## Segnali

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

## SDK Plugin

Escalated supporta plugin indipendenti dal framework costruiti con il [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk). I plugin vengono scritti una volta in TypeScript e funzionano su tutti i backend Escalated.

### Requisiti

- Node.js 20+
- `@escalated-dev/plugin-runtime` installed in your project

### Installazione dei Plugin

```bash
npm install @escalated-dev/plugin-runtime
npm install @escalated-dev/plugin-slack
npm install @escalated-dev/plugin-jira
```

### Abilitazione Plugin SDK

```python
# settings.py
ESCALATED = {
    # ... existing config ...
    "SDK_ENABLED": True,
}
```

### Come Funziona

SDK plugins run as a long-lived Node.js subprocess managed by `@escalated-dev/plugin-runtime`, communicating with Django over JSON-RPC 2.0 via stdio. Every ticket lifecycle signal is dual-dispatched — first to Django signal handlers, then forwarded to the plugin runtime.

### Creare il Proprio Plugin

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

### Risorse

- [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) — SDK TypeScript per creare plugin
- [Plugin Runtime](https://github.com/escalated-dev/escalated-plugin-runtime) — Host runtime per i plugin
- [Plugin Development Guide](https://github.com/escalated-dev/escalated-docs) — Documentazione completa

See the detailed [SDK Plugin Bridge](#sdk-plugin-bridge) section below for the full architecture, supported `ctx.*` callbacks, hook event mapping, and resilience documentation.

## Bridge Plugin SDK

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

### Requisiti

- Node.js 18+
- `@escalated-dev/plugin-runtime` installed in your project's
  `node_modules`

### Avvio rapido

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

### Resilienza

- The bridge is spawned **lazily** on first use — health-check requests are
  never slowed down.
- If the Node.js runtime crashes it is automatically restarted with
  **exponential backoff** (up to 5 minutes between attempts).
- Action hooks degrade gracefully (drop with a warning) when the runtime is
  unavailable.  Filter hooks return the unmodified value.
- The action queue is capped at 1 000 in-flight entries to prevent memory
  growth.

## Disponibile Anche Per

- **[Escalated for Laravel](https://github.com/escalated-dev/escalated-laravel)** — Pacchetto Laravel Composer
- **[Escalated for Rails](https://github.com/escalated-dev/escalated-rails)** — Motore Ruby on Rails
- **[Escalated for Django](https://github.com/escalated-dev/escalated-django)** — App Django riutilizzabile (sei qui)
- **[Escalated for AdonisJS](https://github.com/escalated-dev/escalated-adonis)** — Pacchetto AdonisJS v6
- **[Escalated for Filament](https://github.com/escalated-dev/escalated-filament)** — Plugin pannello admin Filament v3
- **[Shared Frontend](https://github.com/escalated-dev/escalated)** — Componenti UI Vue 3 + Inertia.js

Stessa architettura, stessa interfaccia Vue, stesse tre modalità di hosting — per ogni framework backend principale.

## Sviluppo

```bash
pip install -e ".[dev]"
pytest
```

## Licenza

MIT

<p align="center">
  <a href="README.ar.md">العربية</a> •
  <a href="README.de.md">Deutsch</a> •
  <a href="../../README.md">English</a> •
  <b>Español</b> •
  <a href="README.fr.md">Français</a> •
  <a href="README.it.md">Italiano</a> •
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
[![FOSSA Status](https://app.fossa.com/api/projects/custom%2B62107%2Fgithub.com%2Fescalated-dev%2Fescalated-django.svg?type=shield)](https://app.fossa.com/projects/custom%2B62107%2Fgithub.com%2Fescalated-dev%2Fescalated-django?ref=badge_shield)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2+-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Un sistema de tickets de soporte completo e integrable para Django. Agrégalo a cualquier aplicación — obtén un helpdesk completo con seguimiento de SLA, reglas de escalamiento, flujos de trabajo de agentes y un portal de clientes. No requiere servicios externos.

> **[escalated.dev](https://escalated.dev)** — Obtenga más información, vea demos y compare las opciones de Cloud vs Auto-hospedado.

**Tres modos de alojamiento.** Ejecute completamente auto-hospedado, sincronice con una nube central para visibilidad multi-aplicación, o redirija todo a la nube. Cambie de modo con un solo cambio de configuración.

## Características

- **Ciclo de vida del ticket** — Crear, asignar, responder, resolver, cerrar, reabrir con transiciones de estado configurables
- **Motor de SLA** — Objetivos de respuesta y resolución por prioridad, cálculo de horas laborales, detección automática de incumplimientos
- **Reglas de escalamiento** — Reglas basadas en condiciones que escalan, repriorizan, reasignan o notifican automáticamente
- **Panel del agente** — Cola de tickets con filtros, acciones masivas, notas internas, respuestas predefinidas
- **Portal del cliente** — Creación de tickets en autoservicio, respuestas y seguimiento de estado
- **Panel de administración** — Gestionar departamentos, políticas de SLA, reglas de escalamiento, etiquetas y ver informes
- **Archivos adjuntos** — Carga con arrastrar y soltar, almacenamiento y límites de tamaño configurables
- **Línea de actividad** — Registro completo de auditoría de cada acción en cada ticket
- **Notificaciones por correo** — Notificaciones configurables por evento con soporte de webhooks
- **Enrutamiento por departamentos** — Organizar agentes en departamentos con asignación automática (round-robin)
- **Sistema de etiquetado** — Categorizar tickets con etiquetas de colores
- **Inertia.js + Vue 3 UI** — Frontend compartido a través de [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)
- **División de tickets** — Dividir una respuesta en un nuevo ticket independiente conservando el contexto original
- **Ticket snooze** — Posponer tickets con preajustes (1h, 4h, mañana, próxima semana); el comando de gestión `python manage.py wake_snoozed_tickets` los reactiva automáticamente según la programación
- **Vistas guardadas / colas personalizadas** — Guardar, nombrar y compartir filtros preestablecidos como vistas de tickets reutilizables
- **Widget de soporte integrable** — Widget ligero `<script>` con búsqueda en KB, formulario de tickets y verificación de estado
- **Hilos de correo electrónico** — Los correos salientes incluyen encabezados `In-Reply-To` y `References` apropiados para el hilo correcto en clientes de correo
- **Plantillas de correo con marca** — Logo, color primario y texto de pie de página configurables para todos los correos salientes
- **Real-time broadcasting** — Transmisión opcional a través de Django Channels con respaldo automático de sondeo
- **Interruptor de base de conocimientos** — Habilitar o deshabilitar la base de conocimientos pública desde la configuración de administración

## Requisitos

- Python 3.10+
- Django 4.2+
- Node.js 18+ (para recursos del frontend)

## Inicio Rápido

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

## Configuración del Frontend

Escalated utiliza Inertia.js con Vue 3. Los componentes del frontend son proporcionados por el paquete npm [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated).

### Contenido de Tailwind

Agregue el paquete Escalated a la configuración `content` de Tailwind para que sus clases no sean eliminadas:

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### Resolución de Páginas

Agregue las páginas de Escalated a su resolver de páginas de Inertia:

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

### Temas (Opcional)

Registre el `EscalatedPlugin` para renderizar las páginas de Escalated dentro del diseño de su aplicación — no se necesita duplicación de páginas:

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

Consulte el [README de `@escalated-dev/escalated`](https://github.com/escalated-dev/escalated) para la documentación completa de temas y propiedades CSS personalizadas.

## Modos de Alojamiento

### Self-Hosted (predeterminado)

Todo permanece en su base de datos. Sin llamadas externas. Autonomía total.

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### Sincronizado

Base de datos local + sincronización automática con `cloud.escalated.dev` para bandeja de entrada unificada en múltiples aplicaciones. Si la nube no está disponible, su aplicación sigue funcionando — los eventos se ponen en cola y se reintentan.

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

### Nube

Todos los datos de tickets se envían a la API en la nube. Su aplicación maneja la autenticación y renderiza la interfaz, pero el almacenamiento vive en la nube.

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

Los tres modos comparten las mismas vistas, interfaz y lógica de negocio. El patrón de driver se encarga del resto.

## Configuración

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

## Comandos de Gestión

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

## Rutas

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

## Señales

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

## SDK de Plugins

Escalated soporta plugins agnósticos al framework construidos con el [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk). Los plugins se escriben una vez en TypeScript y funcionan en todos los backends de Escalated.

### Requisitos

- Node.js 20+
- `@escalated-dev/plugin-runtime` installed in your project

### Instalación de Plugins

```bash
npm install @escalated-dev/plugin-runtime
npm install @escalated-dev/plugin-slack
npm install @escalated-dev/plugin-jira
```

### Habilitando Plugins SDK

```python
# settings.py
ESCALATED = {
    # ... existing config ...
    "SDK_ENABLED": True,
}
```

### Cómo Funciona

SDK plugins run as a long-lived Node.js subprocess managed by `@escalated-dev/plugin-runtime`, communicating with Django over JSON-RPC 2.0 via stdio. Every ticket lifecycle signal is dual-dispatched — first to Django signal handlers, then forwarded to the plugin runtime.

### Creando Tu Propio Plugin

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

### Recursos

- [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) — SDK de TypeScript para crear plugins
- [Plugin Runtime](https://github.com/escalated-dev/escalated-plugin-runtime) — Host de tiempo de ejecución para plugins
- [Plugin Development Guide](https://github.com/escalated-dev/escalated-docs) — Documentación completa

See the detailed [SDK Plugin Bridge](#sdk-plugin-bridge) section below for the full architecture, supported `ctx.*` callbacks, hook event mapping, and resilience documentation.

## Puente de Plugins SDK

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

### Requisitos

- Node.js 18+
- `@escalated-dev/plugin-runtime` installed in your project's
  `node_modules`

### Inicio rápido

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

### Resiliencia

- The bridge is spawned **lazily** on first use — health-check requests are
  never slowed down.
- If the Node.js runtime crashes it is automatically restarted with
  **exponential backoff** (up to 5 minutes between attempts).
- Action hooks degrade gracefully (drop with a warning) when the runtime is
  unavailable.  Filter hooks return the unmodified value.
- The action queue is capped at 1 000 in-flight entries to prevent memory
  growth.

## También Disponible Para

- **[Escalated for Laravel](https://github.com/escalated-dev/escalated-laravel)** — Paquete Laravel Composer
- **[Escalated for Rails](https://github.com/escalated-dev/escalated-rails)** — Motor Ruby on Rails
- **[Escalated for Django](https://github.com/escalated-dev/escalated-django)** — Aplicación reutilizable de Django (estás aquí)
- **[Escalated for AdonisJS](https://github.com/escalated-dev/escalated-adonis)** — Paquete AdonisJS v6
- **[Escalated for Filament](https://github.com/escalated-dev/escalated-filament)** — Plugin de panel de administración Filament v3
- **[Shared Frontend](https://github.com/escalated-dev/escalated)** — Componentes de UI Vue 3 + Inertia.js

Misma arquitectura, misma interfaz Vue, mismos tres modos de alojamiento — para cada framework backend importante.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest
```

## Licencia

MIT

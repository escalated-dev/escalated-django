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
  <a href="README.pl.md">Polski</a> •
  <b>Português (BR)</b> •
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

Um sistema de tickets de suporte completo e integrável para Django. Adicione-o a qualquer aplicação — obtenha um helpdesk completo com rastreamento de SLA, regras de escalonamento, fluxos de trabalho de agentes e um portal do cliente. Nenhum serviço externo necessário.

> **[escalated.dev](https://escalated.dev)** — Saiba mais, veja demos e compare as opções Cloud vs Auto-hospedado.

**Três modos de hospedagem.** Execute totalmente auto-hospedado, sincronize com uma nuvem central para visibilidade multi-aplicação, ou redirecione tudo para a nuvem. Mude de modo com uma única alteração de configuração.

## Funcionalidades

- **Ciclo de vida do ticket** — Criar, atribuir, responder, resolver, fechar, reabrir com transições de status configuráveis
- **Motor de SLA** — Metas de resposta e resolução por prioridade, cálculo de horário comercial, detecção automática de violações
- **Regras de escalonamento** — Regras baseadas em condições que escalonam, repriorizam, reatribuem ou notificam automaticamente
- **Painel do agente** — Fila de tickets com filtros, ações em massa, notas internas, respostas predefinidas
- **Portal do cliente** — Criação de tickets em autoatendimento, respostas e acompanhamento de status
- **Painel de administração** — Gerenciar departamentos, políticas de SLA, regras de escalonamento, tags e ver relatórios
- **Anexos de arquivos** — Upload com arrastar e soltar, armazenamento configurável e limites de tamanho
- **Linha do tempo de atividades** — Log de auditoria completo de cada ação em cada ticket
- **Notificações por email** — Notificações configuráveis por evento com suporte a webhooks
- **Roteamento por departamento** — Organizar agentes em departamentos com atribuição automática (round-robin)
- **Sistema de tags** — Categorizar tickets com tags coloridas
- **Inertia.js + Vue 3 UI** — Frontend compartilhado via [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)
- **Divisão de tickets** — Dividir uma resposta em um novo ticket independente preservando o contexto original
- **Ticket snooze** — Adiar tickets com predefinições (1h, 4h, amanhã, próxima semana); o comando `python manage.py wake_snoozed_tickets` os reativa automaticamente
- **Visualizações salvas / filas personalizadas** — Salvar, nomear e compartilhar presets de filtros como visualizações de tickets reutilizáveis
- **Widget de suporte integrável** — Widget leve `<script>` com busca na KB, formulário de tickets e verificação de status
- **Threading de email** — Emails enviados incluem cabeçalhos `In-Reply-To` e `References` para threading correto em clientes de email
- **Templates de email com marca** — Logo, cor primária e texto do rodapé configuráveis para todos os emails enviados
- **Real-time broadcasting** — Broadcasting opcional via Django Channels com fallback automático de polling
- **Toggle da base de conhecimento** — Habilitar ou desabilitar a base de conhecimento pública nas configurações de administração

## Requisitos

- Python 3.10+
- Django 4.2+
- Node.js 18+ (para recursos do frontend)

## Início Rápido

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

## Configuração do Frontend

O Escalated usa Inertia.js com Vue 3. Os componentes do frontend são fornecidos pelo pacote npm [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated).

### Conteúdo Tailwind

Adicione o pacote Escalated à configuração `content` do Tailwind para que suas classes não sejam removidas:

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### Resolvedor de Páginas

Adicione as páginas do Escalated ao seu resolver de páginas do Inertia:

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

Registre o `EscalatedPlugin` para renderizar as páginas do Escalated dentro do layout do seu aplicativo — sem necessidade de duplicação de páginas:

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

Consulte o [README do `@escalated-dev/escalated`](https://github.com/escalated-dev/escalated) para documentação completa de temas e propriedades CSS personalizadas.

## Modos de Hospedagem

### Self-Hosted (padrão)

Tudo permanece no seu banco de dados. Sem chamadas externas. Autonomia total.

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### Sincronizado

Banco de dados local + sincronização automática com `cloud.escalated.dev` para caixa de entrada unificada em múltiplas aplicações. Se a nuvem estiver inacessível, seu aplicativo continua funcionando — os eventos entram na fila e são reenviados.

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

### Nuvem

Todos os dados de tickets são proxy para a API na nuvem. Seu aplicativo lida com autenticação e renderiza a interface, mas o armazenamento fica na nuvem.

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

Os três modos compartilham as mesmas views, interface e lógica de negócios. O padrão de driver cuida do resto.

## Configuração

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

## Comandos de Gerenciamento

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

## Rotas

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

## Sinais

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

O Escalated suporta plugins agnósticos de framework construídos com o [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk). Os plugins são escritos uma vez em TypeScript e funcionam em todos os backends do Escalated.

### Requisitos

- Node.js 20+
- `@escalated-dev/plugin-runtime` installed in your project

### Instalando Plugins

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

### Como Funciona

SDK plugins run as a long-lived Node.js subprocess managed by `@escalated-dev/plugin-runtime`, communicating with Django over JSON-RPC 2.0 via stdio. Every ticket lifecycle signal is dual-dispatched — first to Django signal handlers, then forwarded to the plugin runtime.

### Criando Seu Próprio Plugin

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

- [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) — SDK TypeScript para criar plugins
- [Plugin Runtime](https://github.com/escalated-dev/escalated-plugin-runtime) — Host de runtime para plugins
- [Plugin Development Guide](https://github.com/escalated-dev/escalated-docs) — Documentação completa

See the detailed [SDK Plugin Bridge](#sdk-plugin-bridge) section below for the full architecture, supported `ctx.*` callbacks, hook event mapping, and resilience documentation.

## Ponte de Plugins SDK

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

### Início rápido

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

### Resiliência

- The bridge is spawned **lazily** on first use — health-check requests are
  never slowed down.
- If the Node.js runtime crashes it is automatically restarted with
  **exponential backoff** (up to 5 minutes between attempts).
- Action hooks degrade gracefully (drop with a warning) when the runtime is
  unavailable.  Filter hooks return the unmodified value.
- The action queue is capped at 1 000 in-flight entries to prevent memory
  growth.

## Também Disponível Para

- **[Escalated for Laravel](https://github.com/escalated-dev/escalated-laravel)** — Pacote Laravel Composer
- **[Escalated for Rails](https://github.com/escalated-dev/escalated-rails)** — Motor Ruby on Rails
- **[Escalated for Django](https://github.com/escalated-dev/escalated-django)** — Aplicativo Django reutilizável (você está aqui)
- **[Escalated for AdonisJS](https://github.com/escalated-dev/escalated-adonis)** — Pacote AdonisJS v6
- **[Escalated for Filament](https://github.com/escalated-dev/escalated-filament)** — Plugin de painel administrativo Filament v3
- **[Shared Frontend](https://github.com/escalated-dev/escalated)** — Componentes de UI Vue 3 + Inertia.js

Mesma arquitetura, mesma interface Vue, mesmos três modos de hospedagem — para cada framework backend importante.

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest
```

## Licença

MIT

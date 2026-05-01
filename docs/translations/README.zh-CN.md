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
  <a href="README.pt-BR.md">Português (BR)</a> •
  <a href="README.ru.md">Русский</a> •
  <a href="README.tr.md">Türkçe</a> •
  <b>简体中文</b>
</p>

# Escalated for Django

[![Tests](https://github.com/escalated-dev/escalated-django/actions/workflows/run-tests.yml/badge.svg)](https://github.com/escalated-dev/escalated-django/actions/workflows/run-tests.yml)
[![FOSSA Status](https://app.fossa.com/api/projects/custom%2B62107%2Fgithub.com%2Fescalated-dev%2Fescalated-django.svg?type=shield)](https://app.fossa.com/projects/custom%2B62107%2Fgithub.com%2Fescalated-dev%2Fescalated-django?ref=badge_shield)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2+-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个功能完整、可嵌入的 Django 支持工单系统。将其添加到任何应用中 — 即可获得完整的帮助台，包含 SLA 跟踪、升级规则、客服工作流和客户门户。无需外部服务。

> **[escalated.dev](https://escalated.dev)** — 了解更多、查看演示，并比较云端与自托管选项。

**三种托管模式。** 完全自托管运行，同步到中央云以获得多应用可见性，或将所有内容代理到云端。只需更改一个配置即可切换模式。

## 功能特性

- **工单生命周期** — 创建、分配、回复、解决、关闭、重新打开，支持可配置的状态转换
- **SLA 引擎** — 按优先级的响应和解决目标、工作时间计算、自动违规检测
- **升级规则** — 基于条件的规则，自动升级、重新排列优先级、重新分配或通知
- **客服面板** — 带过滤器、批量操作、内部备注、预设回复的工单队列
- **客户门户** — 自助工单创建、回复和状态跟踪
- **管理面板** — 管理部门、SLA 策略、升级规则、标签和查看报告
- **文件附件** — 拖拽上传，可配置存储和大小限制
- **活动时间线** — 每个工单上每个操作的完整审计日志
- **邮件通知** — 可按事件配置的通知，支持 webhook
- **部门路由** — 将客服组织到部门，支持自动分配（轮询）
- **标签系统** — 使用彩色标签分类工单
- **Inertia.js + Vue 3 UI** — 通过 [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated) 共享前端
- **工单拆分** — 将回复拆分为新的独立工单，同时保留原始上下文
- **Ticket snooze** — 使用预设延迟工单（1小时、4小时、明天、下周）；管理命令 `python manage.py wake_snoozed_tickets` 按计划自动唤醒
- **保存的视图 / 自定义队列** — 将过滤器预设保存、命名并共享为可重用的工单视图
- **可嵌入支持小部件** — 包含知识库搜索、工单表单和状态查询的轻量级 `<script>` 小部件
- **邮件线程** — 发送的邮件包含正确的 `In-Reply-To` 和 `References` 头部，以在邮件客户端中实现正确的线程化
- **品牌邮件模板** — 所有发送邮件的可配置 logo、主色和页脚文本
- **Real-time broadcasting** — 通过 Django Channels 进行可选广播，带有自动轮询回退
- **知识库开关** — 从管理设置中启用或禁用公共知识库

## 环境要求

- Python 3.10+
- Django 4.2+
- Node.js 18+ (用于前端资源)

## 快速开始

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

## 前端设置

Escalated 使用 Inertia.js 和 Vue 3。前端组件由 npm 包 [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated) 提供。

### Tailwind 内容

将 Escalated 包添加到 Tailwind 的 `content` 配置中，以确保其类不会被清除：

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### 页面解析器

将 Escalated 页面添加到您的 Inertia 页面解析器：

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

### 主题（可选）

注册 `EscalatedPlugin` 以在您的应用布局内渲染 Escalated 页面 — 无需页面复制：

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

查看 [`@escalated-dev/escalated` README](https://github.com/escalated-dev/escalated) 以获取完整的主题文档和 CSS 自定义属性。

## 托管模式

### Self-Hosted（默认）

所有数据保留在您的数据库中。无外部调用。完全自主。

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### 同步模式

本地数据库 + 自动同步到 `cloud.escalated.dev` 以实现跨多个应用的统一收件箱。如果云端不可达，您的应用继续工作 — 事件会排队并重试。

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

### 云端

所有工单数据代理到云 API。您的应用处理认证和渲染 UI，但存储在云端。

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

三种模式共享相同的视图、UI 和业务逻辑。驱动模式处理其余部分。

## 配置

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

## 管理命令

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

## 路由

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

## 信号

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

## 插件 SDK

Escalated 支持使用 [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) 构建的框架无关插件。插件用 TypeScript 编写一次，即可在所有 Escalated 后端上运行。

### 环境要求

- Node.js 20+
- `@escalated-dev/plugin-runtime` installed in your project

### 安装插件

```bash
npm install @escalated-dev/plugin-runtime
npm install @escalated-dev/plugin-slack
npm install @escalated-dev/plugin-jira
```

### 启用 SDK 插件

```python
# settings.py
ESCALATED = {
    # ... existing config ...
    "SDK_ENABLED": True,
}
```

### 工作原理

SDK plugins run as a long-lived Node.js subprocess managed by `@escalated-dev/plugin-runtime`, communicating with Django over JSON-RPC 2.0 via stdio. Every ticket lifecycle signal is dual-dispatched — first to Django signal handlers, then forwarded to the plugin runtime.

### 构建自己的插件

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

### 资源

- [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) — 用于构建插件的 TypeScript SDK
- [Plugin Runtime](https://github.com/escalated-dev/escalated-plugin-runtime) — 插件运行时宿主
- [Plugin Development Guide](https://github.com/escalated-dev/escalated-docs) — 完整文档

See the detailed [SDK Plugin Bridge](#sdk-plugin-bridge) section below for the full architecture, supported `ctx.*` callbacks, hook event mapping, and resilience documentation.

## SDK 插件桥接

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

### 环境要求

- Node.js 18+
- `@escalated-dev/plugin-runtime` installed in your project's
  `node_modules`

### 快速开始

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

### 弹性

- The bridge is spawned **lazily** on first use — health-check requests are
  never slowed down.
- If the Node.js runtime crashes it is automatically restarted with
  **exponential backoff** (up to 5 minutes between attempts).
- Action hooks degrade gracefully (drop with a warning) when the runtime is
  unavailable.  Filter hooks return the unmodified value.
- The action queue is capped at 1 000 in-flight entries to prevent memory
  growth.

## 其他框架版本

- **[Escalated for Laravel](https://github.com/escalated-dev/escalated-laravel)** — Laravel Composer 包
- **[Escalated for Rails](https://github.com/escalated-dev/escalated-rails)** — Ruby on Rails 引擎
- **[Escalated for Django](https://github.com/escalated-dev/escalated-django)** — Django 可复用应用（当前页面）
- **[Escalated for AdonisJS](https://github.com/escalated-dev/escalated-adonis)** — AdonisJS v6 包
- **[Escalated for Filament](https://github.com/escalated-dev/escalated-filament)** — Filament v3 管理面板插件
- **[Shared Frontend](https://github.com/escalated-dev/escalated)** — Vue 3 + Inertia.js UI 组件

相同的架构、相同的 Vue UI、相同的三种托管模式 — 适用于每个主流后端框架。

## 开发

```bash
pip install -e ".[dev]"
pytest
```

## 许可证

MIT

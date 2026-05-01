<p align="center">
  <b>العربية</b> •
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
  <a href="README.zh-CN.md">简体中文</a>
</p>

# Escalated for Django

[![Tests](https://github.com/escalated-dev/escalated-django/actions/workflows/run-tests.yml/badge.svg)](https://github.com/escalated-dev/escalated-django/actions/workflows/run-tests.yml)
[![FOSSA Status](https://app.fossa.com/api/projects/custom%2B62107%2Fgithub.com%2Fescalated-dev%2Fescalated-django.svg?type=shield)](https://app.fossa.com/projects/custom%2B62107%2Fgithub.com%2Fescalated-dev%2Fescalated-django?ref=badge_shield)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2+-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

نظام تذاكر دعم متكامل وقابل للتضمين في Django. أضفه إلى أي تطبيق — واحصل على مكتب مساعدة كامل مع تتبع SLA وقواعد التصعيد وسير عمل الوكلاء وبوابة العملاء. لا حاجة لخدمات خارجية.

> **[escalated.dev](https://escalated.dev)** — اعرف المزيد، شاهد العروض التوضيحية، وقارن بين خيارات السحابة والاستضافة الذاتية.

**ثلاثة أوضاع استضافة.** تشغيل مستضاف ذاتياً بالكامل، أو مزامنة مع سحابة مركزية لرؤية متعددة التطبيقات، أو توجيه كل شيء إلى السحابة. التبديل بين الأوضاع بتغيير إعداد واحد.

## الميزات

- **دورة حياة التذكرة** — إنشاء، تعيين، رد، حل، إغلاق، إعادة فتح مع انتقالات حالة قابلة للتهيئة
- **محرك SLA** — أهداف الاستجابة والحل حسب الأولوية، حساب ساعات العمل، كشف تلقائي للانتهاكات
- **قواعد التصعيد** — قواعد قائمة على الشروط تقوم بالتصعيد وإعادة الترتيب وإعادة التعيين أو الإشعار تلقائياً
- **لوحة تحكم الوكيل** — قائمة انتظار التذاكر مع فلاتر، إجراءات جماعية، ملاحظات داخلية، ردود جاهزة
- **بوابة العملاء** — إنشاء تذاكر ذاتية الخدمة، ردود، وتتبع الحالة
- **لوحة الإدارة** — إدارة الأقسام، سياسات SLA، قواعد التصعيد، العلامات وعرض التقارير
- **مرفقات الملفات** — رفع بالسحب والإفلات مع تخزين قابل للتهيئة وحدود الحجم
- **الجدول الزمني للنشاط** — سجل تدقيق كامل لكل إجراء على كل تذكرة
- **إشعارات البريد الإلكتروني** — إشعارات قابلة للتهيئة لكل حدث مع دعم webhook
- **توجيه الأقسام** — تنظيم الوكلاء في أقسام مع التعيين التلقائي (round-robin)
- **نظام العلامات** — تصنيف التذاكر بعلامات ملونة
- **Inertia.js + Vue 3 UI** — واجهة أمامية مشتركة عبر [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)
- **تقسيم التذاكر** — تقسيم رد إلى تذكرة مستقلة جديدة مع الحفاظ على السياق الأصلي
- **Ticket snooze** — تأجيل التذاكر بإعدادات مسبقة (1 ساعة، 4 ساعات، غداً، الأسبوع القادم)؛ أمر الإدارة `python manage.py wake_snoozed_tickets` يوقظها تلقائياً حسب الجدول
- **العروض المحفوظة / الطوابير المخصصة** — حفظ وتسمية ومشاركة إعدادات الفلاتر كعروض تذاكر قابلة لإعادة الاستخدام
- **عنصر الدعم القابل للتضمين** — عنصر `<script>` خفيف مع بحث قاعدة المعرفة ونموذج تذكرة وفحص الحالة
- **ترابط البريد الإلكتروني** — الرسائل الصادرة تتضمن رؤوس `In-Reply-To` و `References` الصحيحة للترابط الصحيح في عملاء البريد
- **قوالب بريد إلكتروني مع العلامة التجارية** — شعار ولون رئيسي ونص تذييل قابل للتهيئة لجميع الرسائل الصادرة
- **Real-time broadcasting** — بث اختياري عبر Django Channels مع استطلاع احتياطي تلقائي
- **مفتاح قاعدة المعرفة** — تفعيل أو تعطيل قاعدة المعرفة العامة من إعدادات الإدارة

## المتطلبات

- Python 3.10+
- Django 4.2+
- Node.js 18+ (لأصول الواجهة الأمامية)

## البدء السريع

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

## إعداد الواجهة الأمامية

يستخدم Escalated إطار Inertia.js مع Vue 3. يتم توفير مكونات الواجهة الأمامية بواسطة حزمة npm [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated).

### محتوى Tailwind

أضف حزمة Escalated إلى إعداد `content` في Tailwind حتى لا يتم حذف فئاتها:

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### محلل الصفحات

أضف صفحات Escalated إلى محلل صفحات Inertia الخاص بك:

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

### التخصيص (اختياري)

قم بتسجيل `EscalatedPlugin` لعرض صفحات Escalated داخل تخطيط تطبيقك — لا حاجة لتكرار الصفحات:

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

راجع [ملف `@escalated-dev/escalated` README](https://github.com/escalated-dev/escalated) للحصول على وثائق السمات الكاملة وخصائص CSS المخصصة.

## أوضاع الاستضافة

### Self-Hosted (الافتراضي)

كل شيء يبقى في قاعدة بياناتك. لا اتصالات خارجية. استقلالية كاملة.

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### متزامن

قاعدة بيانات محلية + مزامنة تلقائية مع `cloud.escalated.dev` لصندوق وارد موحد عبر تطبيقات متعددة. إذا كانت السحابة غير قابلة للوصول، يستمر تطبيقك في العمل — الأحداث تُوضع في قائمة الانتظار ويُعاد المحاولة.

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

### السحابة

جميع بيانات التذاكر تُوجَّه عبر واجهة API السحابية. تطبيقك يتعامل مع المصادقة ويعرض الواجهة، لكن التخزين يكون في السحابة.

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

تشترك جميع الأوضاع الثلاثة في نفس العروض وواجهة المستخدم ومنطق الأعمال. نمط المحرك يتعامل مع الباقي.

## التهيئة

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

## أوامر الإدارة

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

## المسارات

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

## الإشارات

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

## SDK الإضافات

يدعم Escalated إضافات مستقلة عن إطار العمل مبنية بـ [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk). تُكتب الإضافات مرة واحدة بـ TypeScript وتعمل عبر جميع خلفيات Escalated.

### المتطلبات

- Node.js 20+
- `@escalated-dev/plugin-runtime` installed in your project

### تثبيت الإضافات

```bash
npm install @escalated-dev/plugin-runtime
npm install @escalated-dev/plugin-slack
npm install @escalated-dev/plugin-jira
```

### تفعيل إضافات SDK

```python
# settings.py
ESCALATED = {
    # ... existing config ...
    "SDK_ENABLED": True,
}
```

### كيف يعمل

SDK plugins run as a long-lived Node.js subprocess managed by `@escalated-dev/plugin-runtime`, communicating with Django over JSON-RPC 2.0 via stdio. Every ticket lifecycle signal is dual-dispatched — first to Django signal handlers, then forwarded to the plugin runtime.

### بناء الإضافة الخاصة بك

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

### الموارد

- [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) — حزمة تطوير TypeScript لبناء الإضافات
- [Plugin Runtime](https://github.com/escalated-dev/escalated-plugin-runtime) — مضيف وقت التشغيل للإضافات
- [Plugin Development Guide](https://github.com/escalated-dev/escalated-docs) — التوثيق الكامل

See the detailed [SDK Plugin Bridge](#sdk-plugin-bridge) section below for the full architecture, supported `ctx.*` callbacks, hook event mapping, and resilience documentation.

## جسر إضافات SDK

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

### المتطلبات

- Node.js 18+
- `@escalated-dev/plugin-runtime` installed in your project's
  `node_modules`

### البدء السريع

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

### المرونة

- The bridge is spawned **lazily** on first use — health-check requests are
  never slowed down.
- If the Node.js runtime crashes it is automatically restarted with
  **exponential backoff** (up to 5 minutes between attempts).
- Action hooks degrade gracefully (drop with a warning) when the runtime is
  unavailable.  Filter hooks return the unmodified value.
- The action queue is capped at 1 000 in-flight entries to prevent memory
  growth.

## متوفر أيضاً لـ

- **[Escalated for Laravel](https://github.com/escalated-dev/escalated-laravel)** — حزمة Laravel Composer
- **[Escalated for Rails](https://github.com/escalated-dev/escalated-rails)** — محرك Ruby on Rails
- **[Escalated for Django](https://github.com/escalated-dev/escalated-django)** — تطبيق Django قابل لإعادة الاستخدام (أنت هنا)
- **[Escalated for AdonisJS](https://github.com/escalated-dev/escalated-adonis)** — حزمة AdonisJS v6
- **[Escalated for Filament](https://github.com/escalated-dev/escalated-filament)** — إضافة لوحة إدارة Filament v3
- **[Shared Frontend](https://github.com/escalated-dev/escalated)** — مكونات واجهة المستخدم Vue 3 + Inertia.js

نفس البنية، نفس واجهة Vue، نفس أوضاع الاستضافة الثلاثة — لكل إطار عمل خلفي رئيسي.

## التطوير

```bash
pip install -e ".[dev]"
pytest
```

## الرخصة

MIT

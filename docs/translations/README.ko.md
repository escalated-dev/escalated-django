<p align="center">
  <a href="README.ar.md">العربية</a> •
  <a href="README.de.md">Deutsch</a> •
  <a href="../../README.md">English</a> •
  <a href="README.es.md">Español</a> •
  <a href="README.fr.md">Français</a> •
  <a href="README.it.md">Italiano</a> •
  <a href="README.ja.md">日本語</a> •
  <b>한국어</b> •
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

Django용 완전한 기능을 갖춘 임베드 가능한 지원 티켓 시스템입니다. 어떤 앱에든 추가하면 SLA 추적, 에스컬레이션 규칙, 상담원 워크플로우, 고객 포털을 갖춘 완전한 헬프데스크를 얻을 수 있습니다. 외부 서비스가 필요 없습니다.

> **[escalated.dev](https://escalated.dev)** — 자세히 알아보고, 데모를 보고, 클라우드와 셀프호스팅 옵션을 비교하세요.

**세 가지 호스팅 모드.** 완전한 셀프호스팅, 멀티앱 가시성을 위한 중앙 클라우드 동기화, 또는 모든 것을 클라우드로 프록시. 설정 하나만 변경하면 모드를 전환할 수 있습니다.

## 기능

- **티켓 라이프사이클** — 구성 가능한 상태 전환으로 생성, 할당, 답변, 해결, 닫기, 재개
- **SLA 엔진** — 우선순위별 응답 및 해결 목표, 업무 시간 계산, 자동 위반 감지
- **에스컬레이션 규칙** — 자동으로 에스컬레이트, 우선순위 변경, 재할당 또는 알림하는 조건 기반 규칙
- **에이전트 대시보드** — 필터, 대량 작업, 내부 메모, 정형 응답이 포함된 티켓 큐
- **고객 포털** — 셀프서비스 티켓 생성, 답변, 상태 추적
- **관리자 패널** — 부서, SLA 정책, 에스컬레이션 규칙, 태그 관리 및 보고서 보기
- **파일 첨부** — 드래그 앤 드롭 업로드, 구성 가능한 스토리지 및 크기 제한
- **활동 타임라인** — 모든 티켓의 모든 작업에 대한 전체 감사 로그
- **이메일 알림** — 웹훅 지원을 포함한 이벤트별 구성 가능한 알림
- **부서 라우팅** — 에이전트를 부서별로 조직하고 자동 할당 (라운드 로빈)
- **태그 시스템** — 색상 태그로 티켓 분류
- **Inertia.js + Vue 3 UI** — [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)를 통한 공유 프론트엔드
- **티켓 분할** — 원래 컨텍스트를 보존하면서 답변을 새로운 독립 티켓으로 분할
- **Ticket snooze** — 프리셋으로 티켓 스누즈 (1시간, 4시간, 내일, 다음 주); 관리 명령어 `python manage.py wake_snoozed_tickets`가 예정대로 자동으로 깨움
- **저장된 뷰 / 커스텀 큐** — 필터 프리셋을 재사용 가능한 티켓 뷰로 저장, 명명 및 공유
- **임베드 가능한 지원 위젯** — KB 검색, 티켓 폼, 상태 확인이 포함된 경량 `<script>` 위젯
- **이메일 스레딩** — 발신 이메일에 적절한 `In-Reply-To` 및 `References` 헤더를 포함하여 메일 클라이언트에서 올바른 스레딩 지원
- **브랜드 이메일 템플릿** — 모든 발신 이메일에 대해 로고, 기본 색상, 바닥글 텍스트 구성 가능
- **Real-time broadcasting** — Django Channels를 통한 선택적 브로드캐스팅, 자동 폴링 폴백 포함
- **지식 베이스 토글** — 관리자 설정에서 공개 지식 베이스 활성화 또는 비활성화

## 요구 사항

- Python 3.10+
- Django 4.2+
- Node.js 18+ (프론트엔드 자산용)

## 빠른 시작

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

## 프론트엔드 설정

Escalated는 Inertia.js와 Vue 3를 사용합니다. 프론트엔드 컴포넌트는 npm 패키지 [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)에서 제공됩니다.

### Tailwind 콘텐츠

Escalated 패키지를 Tailwind `content` 설정에 추가하여 클래스가 제거되지 않도록 하세요:

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### 페이지 리졸버

Escalated 페이지를 Inertia 페이지 리줄버에 추가하세요:

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

### 테마 설정 (선택사항)

`EscalatedPlugin`을 등록하여 앱의 레이아웃 내에서 Escalated 페이지를 렌더링하세요 — 페이지 복제가 필요 없습니다:

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

전체 테마 문서와 CSS 커스텀 속성에 대해서는 [`@escalated-dev/escalated` README](https://github.com/escalated-dev/escalated)를 참조하세요.

## 호스팅 모드

### Self-Hosted (기본값)

모든 것이 데이터베이스에 유지됩니다. 외부 호출 없음. 완전한 자율성.

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### 동기화

로컬 데이터베이스 + `cloud.escalated.dev`로의 자동 동기화로 여러 앱에 걸친 통합 수신함. 클라우드에 연결할 수 없는 경우 앱은 계속 작동합니다 — 이벤트가 대기열에 추가되고 재시도됩니다.

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

### 클라우드

모든 티켓 데이터가 클라우드 API로 프록시됩니다. 앱이 인증과 UI 렌더링을 처리하지만 저장소는 클라우드에 있습니다.

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

세 가지 모드 모두 동일한 뷰, UI 및 비즈니스 로직을 공유합니다. 드라이버 패턴이 나머지를 처리합니다.

## 설정

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

## 관리 명령어

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

## 라우트

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

## 시그널

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

## 플러그인 SDK

Escalated는 [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk)로 구축된 프레임워크 독립적인 플러그인을 지원합니다. 플러그인은 TypeScript로 한 번 작성하면 모든 Escalated 백엔드에서 작동합니다.

### 요구 사항

- Node.js 20+
- `@escalated-dev/plugin-runtime` installed in your project

### 플러그인 설치

```bash
npm install @escalated-dev/plugin-runtime
npm install @escalated-dev/plugin-slack
npm install @escalated-dev/plugin-jira
```

### SDK 플러그인 활성화

```python
# settings.py
ESCALATED = {
    # ... existing config ...
    "SDK_ENABLED": True,
}
```

### 작동 방식

SDK plugins run as a long-lived Node.js subprocess managed by `@escalated-dev/plugin-runtime`, communicating with Django over JSON-RPC 2.0 via stdio. Every ticket lifecycle signal is dual-dispatched — first to Django signal handlers, then forwarded to the plugin runtime.

### 자체 플러그인 만들기

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

### 리소스

- [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) — 플러그인 구축을 위한 TypeScript SDK
- [Plugin Runtime](https://github.com/escalated-dev/escalated-plugin-runtime) — 플러그인용 런타임 호스트
- [Plugin Development Guide](https://github.com/escalated-dev/escalated-docs) — 전체 문서

See the detailed [SDK Plugin Bridge](#sdk-plugin-bridge) section below for the full architecture, supported `ctx.*` callbacks, hook event mapping, and resilience documentation.

## SDK 플러그인 브릿지

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

### 요구 사항

- Node.js 18+
- `@escalated-dev/plugin-runtime` installed in your project's
  `node_modules`

### 빠른 시작

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

### 회복력

- The bridge is spawned **lazily** on first use — health-check requests are
  never slowed down.
- If the Node.js runtime crashes it is automatically restarted with
  **exponential backoff** (up to 5 minutes between attempts).
- Action hooks degrade gracefully (drop with a warning) when the runtime is
  unavailable.  Filter hooks return the unmodified value.
- The action queue is capped at 1 000 in-flight entries to prevent memory
  growth.

## 다른 프레임워크에서도 이용 가능

- **[Escalated for Laravel](https://github.com/escalated-dev/escalated-laravel)** — Laravel Composer 패키지
- **[Escalated for Rails](https://github.com/escalated-dev/escalated-rails)** — Ruby on Rails 엔진
- **[Escalated for Django](https://github.com/escalated-dev/escalated-django)** — Django 재사용 앱 (현재 페이지)
- **[Escalated for AdonisJS](https://github.com/escalated-dev/escalated-adonis)** — AdonisJS v6 패키지
- **[Escalated for Filament](https://github.com/escalated-dev/escalated-filament)** — Filament v3 관리 패널 플러그인
- **[Shared Frontend](https://github.com/escalated-dev/escalated)** — Vue 3 + Inertia.js UI 컴포넌트

동일한 아키텍처, 동일한 Vue UI, 동일한 세 가지 호스팅 모드 — 모든 주요 백엔드 프레임워크에 대응.

## 개발

```bash
pip install -e ".[dev]"
pytest
```

## 라이선스

MIT

<p align="center">
  <a href="README.ar.md">العربية</a> •
  <a href="README.de.md">Deutsch</a> •
  <a href="../../README.md">English</a> •
  <a href="README.es.md">Español</a> •
  <a href="README.fr.md">Français</a> •
  <a href="README.it.md">Italiano</a> •
  <b>日本語</b> •
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

Django用のフル機能で埋め込み可能なサポートチケットシステム。任意のアプリに導入するだけで、SLA追跡、エスカレーションルール、エージェントワークフロー、カスタマーポータルを備えた完全なヘルプデスクが手に入ります。外部サービスは不要です。

> **[escalated.dev](https://escalated.dev)** — 詳細の確認、デモの閲覧、クラウドとセルフホストのオプション比較はこちら。

**3つのホスティングモード。** 完全セルフホスト、マルチアプリの可視性のためのセントラルクラウドへの同期、またはすべてをクラウドにプロキシ。設定を1つ変更するだけでモードを切り替えられます。

## 機能

- **チケットのライフサイクル** — 設定可能なステータス遷移による作成、割り当て、返信、解決、クローズ、再オープン
- **SLAエンジン** — 優先度別の応答・解決目標、営業時間計算、自動違反検出
- **エスカレーションルール** — 自動的にエスカレート、優先度変更、再割り当て、通知する条件ベースのルール
- **エージェントダッシュボード** — フィルター、一括操作、内部メモ、定型応答付きのチケットキュー
- **カスタマーポータル** — セルフサービスのチケット作成、返信、ステータス追跡
- **管理パネル** — 部門、SLAポリシー、エスカレーションルール、タグの管理とレポートの表示
- **ファイル添付** — ドラッグ＆ドロップアップロード、設定可能なストレージとサイズ制限
- **アクティビティタイムライン** — すべてのチケットのすべてのアクションの完全な監査ログ
- **メール通知** — Webhookサポート付きの設定可能なイベント単位の通知
- **部門ルーティング** — エージェントを部門に整理し、自動割り当て（ラウンドロビン）
- **タグ付けシステム** — 色付きタグでチケットを分類
- **Inertia.js + Vue 3 UI** — [`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated) による共有フロントエンド
- **チケットの分割** — 元のコンテキストを保持しながら返信を新しい独立チケットに分割
- **Ticket snooze** — プリセットでチケットをスヌーズ（1時間、4時間、明日、来週）、管理コマンド `python manage.py wake_snoozed_tickets` がスケジュールに従って自動的に起動
- **保存済みビュー / カスタムキュー** — フィルタープリセットを再利用可能なチケットビューとして保存、命名、共有
- **埋め込み可能なサポートウィジェット** — KB検索、チケットフォーム、ステータス確認付きの軽量`<script>`ウィジェット
- **メールスレッディング** — 送信メールに適切な`In-Reply-To`および`References`ヘッダーを含め、メールクライアントでの正しいスレッディングを実現
- **ブランドメールテンプレート** — すべての送信メールのロゴ、プライマリカラー、フッターテキストを設定可能
- **Real-time broadcasting** — Django Channelsによるオプトインブロードキャスト、自動ポーリングフォールバック付き
- **ナレッジベースの切り替え** — 管理設定から公開ナレッジベースを有効/無効に切り替え

## 要件

- Python 3.10+
- Django 4.2+
- Node.js 18+ (フロントエンドアセット用)

## クイックスタート

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

## フロントエンドのセットアップ

EscalatedはInertia.jsとVue 3を使用します。フロントエンドコンポーネントはnpmパッケージ[`@escalated-dev/escalated`](https://github.com/escalated-dev/escalated)で提供されます。

### Tailwindコンテンツ

EscalatedパッケージをTailwindの`content`設定に追加して、そのクラスがパージされないようにします：

```js
// tailwind.config.js
content: [
    // ... your existing paths
    './node_modules/@escalated-dev/escalated/src/**/*.vue',
],
```

### ページリゾルバー

EscalatedのページをInertiaページリゾルバーに追加します：

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

### テーマ設定（オプション）

`EscalatedPlugin`を登録して、アプリのレイアウト内でEscalatedページをレンダリングします — ページの複製は不要です：

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

テーマの完全なドキュメントとCSSカスタムプロパティについては[`@escalated-dev/escalated` README](https://github.com/escalated-dev/escalated)を参照してください。

## ホスティングモード

### Self-Hosted（デフォルト）

すべてがデータベースに保存されます。外部呼び出しなし。完全な自律性。

```python
ESCALATED = {
    "MODE": "self_hosted",
}
```

### 同期モード

ローカルデータベース + `cloud.escalated.dev`への自動同期で複数アプリにわたる統合受信箱。クラウドに到達できない場合、アプリは動作を継続します — イベントはキューに入り、リトライされます。

```python
ESCALATED = {
    "MODE": "synced",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

### クラウド

すべてのチケットデータはクラウドAPIにプロキシされます。アプリが認証とUIのレンダリングを処理しますが、ストレージはクラウドにあります。

```python
ESCALATED = {
    "MODE": "cloud",
    "HOSTED_API_URL": "https://cloud.escalated.dev/api/v1",
    "HOSTED_API_KEY": "your-api-key",
}
```

3つのモードすべてが同じビュー、UI、ビジネスロジックを共有します。ドライバーパターンが残りを処理します。

## 設定

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

## 管理コマンド

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

## ルート

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

## シグナル

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

## プラグインSDK

Escalatedは[Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk)で構築されたフレームワーク非依存のプラグインをサポートしています。プラグインはTypeScriptで一度書くだけで、すべてのEscalatedバックエンドで動作します。

### 要件

- Node.js 20+
- `@escalated-dev/plugin-runtime` installed in your project

### プラグインのインストール

```bash
npm install @escalated-dev/plugin-runtime
npm install @escalated-dev/plugin-slack
npm install @escalated-dev/plugin-jira
```

### SDKプラグインの有効化

```python
# settings.py
ESCALATED = {
    # ... existing config ...
    "SDK_ENABLED": True,
}
```

### 仕組み

SDK plugins run as a long-lived Node.js subprocess managed by `@escalated-dev/plugin-runtime`, communicating with Django over JSON-RPC 2.0 via stdio. Every ticket lifecycle signal is dual-dispatched — first to Django signal handlers, then forwarded to the plugin runtime.

### 独自プラグインの作成

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

### リソース

- [Plugin SDK](https://github.com/escalated-dev/escalated-plugin-sdk) — プラグイン構築用TypeScript SDK
- [Plugin Runtime](https://github.com/escalated-dev/escalated-plugin-runtime) — プラグイン用ランタイムホスト
- [Plugin Development Guide](https://github.com/escalated-dev/escalated-docs) — 完全なドキュメント

See the detailed [SDK Plugin Bridge](#sdk-plugin-bridge) section below for the full architecture, supported `ctx.*` callbacks, hook event mapping, and resilience documentation.

## SDKプラグインブリッジ

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

### 要件

- Node.js 18+
- `@escalated-dev/plugin-runtime` installed in your project's
  `node_modules`

### クイックスタート

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

### レジリエンス

- The bridge is spawned **lazily** on first use — health-check requests are
  never slowed down.
- If the Node.js runtime crashes it is automatically restarted with
  **exponential backoff** (up to 5 minutes between attempts).
- Action hooks degrade gracefully (drop with a warning) when the runtime is
  unavailable.  Filter hooks return the unmodified value.
- The action queue is capped at 1 000 in-flight entries to prevent memory
  growth.

## 他のフレームワーク向けも提供

- **[Escalated for Laravel](https://github.com/escalated-dev/escalated-laravel)** — Laravel Composerパッケージ
- **[Escalated for Rails](https://github.com/escalated-dev/escalated-rails)** — Ruby on Railsエンジン
- **[Escalated for Django](https://github.com/escalated-dev/escalated-django)** — Django再利用可能アプリ（現在のページ）
- **[Escalated for AdonisJS](https://github.com/escalated-dev/escalated-adonis)** — AdonisJS v6パッケージ
- **[Escalated for Filament](https://github.com/escalated-dev/escalated-filament)** — Filament v3管理パネルプラグイン
- **[Shared Frontend](https://github.com/escalated-dev/escalated)** — Vue 3 + Inertia.js UIコンポーネント

同じアーキテクチャ、同じVue UI、同じ3つのホスティングモード — すべての主要バックエンドフレームワークに対応。

## 開発

```bash
pip install -e ".[dev]"
pytest
```

## ライセンス

MIT

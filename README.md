<p align="center"><sub>
  <a href="docs/translations/README.ar.md">العربية</a> ·
  <a href="docs/translations/README.de.md">Deutsch</a> ·
  <b>English</b> ·
  <a href="docs/translations/README.es.md">Español</a> ·
  <a href="docs/translations/README.fr.md">Français</a> ·
  <a href="docs/translations/README.it.md">Italiano</a> ·
  <a href="docs/translations/README.ja.md">日本語</a> ·
  <a href="docs/translations/README.ko.md">한국어</a> ·
  <a href="docs/translations/README.nl.md">Nederlands</a> ·
  <a href="docs/translations/README.pl.md">Polski</a> ·
  <a href="docs/translations/README.pt-BR.md">Português (BR)</a> ·
  <a href="docs/translations/README.ru.md">Русский</a> ·
  <a href="docs/translations/README.tr.md">Türkçe</a> ·
  <a href="docs/translations/README.zh-CN.md">简体中文</a>
</sub></p>

<p align="center">
  <a href="https://escalated.dev"><img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/logo.png" width="72" height="72" alt="Escalated"></a>
</p>

<h1 align="center">Escalated for Django</h1>

<p align="center">
  Add a complete helpdesk to your Django app.<br>
  Tickets, SLAs, escalation rules, an agent inbox and a customer portal, running on your own database.
</p>

<p align="center">
  <a href="https://escalated.dev"><b>Website</b></a> ·
  <a href="https://escalated.dev/docs"><b>Docs</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="CHANGELOG.md"><b>Changelog</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="The Escalated agent inbox: saved views with counts, SLA countdowns and priorities on every ticket" width="100%">
</picture>

## What it does

<table>
  <tr>
    <td width="40%">
      <h3>An inbox your agents can work in all day</h3>
      Conversation, internal notes, canned replies and SLA timers on one screen. Tickets also arrive by email through Mailgun, Postmark, SES or IMAP.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="A ticket open in the agent workspace with the reply composer">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="The admin reports page with response times, CSAT and SLA breaches">
      </picture>
    </td>
    <td width="40%">
      <h3>SLAs and escalation rules you can see</h3>
      Response and resolution targets per priority with business hours, rules that escalate or reassign when they slip, and reports on breaches.
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>A customer portal that's already built</h3>
      Customers open tickets, reply and check status inside your app. Embed the widget on other sites with one script tag.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="The customer portal ticket list">
      </picture>
    </td>
  </tr>
</table>

## Features

<table>
<tr>
<td width="33%" valign="top">

**Tickets and inbox**
- Full lifecycle with status transitions
- Queue filters and bulk actions
- Internal notes and canned responses
- Split a reply into a new ticket
- Snooze with presets and auto-wake
- Saved views and shared queues

</td>
<td width="33%" valign="top">

**SLAs and escalation**
- Per-priority response and resolution targets
- Business hours and breach detection
- Rules that escalate, reassign or notify
- Department routing with round-robin

</td>
<td width="33%" valign="top">

**Customers**
- Self-service customer portal
- Embeddable widget with KB search
- Public knowledge base you can switch off

</td>
</tr>
<tr>
<td width="33%" valign="top">

**Email**
- Inbound via Mailgun, Postmark, SES or IMAP
- Threaded replies in mail clients
- Branded email templates
- Per-event notifications and webhooks

</td>
<td width="33%" valign="top">

**Admin and access**
- Departments, SLAs, rules, tags and reports
- Roles and permissions as an install switch
- Activity timeline on every ticket

</td>
<td width="33%" valign="top">

**Under the hood**
- Shared Vue 3 and Inertia.js UI
- Uploads with storage and size limits
- Colored tags to sort tickets
- Django Channels real-time with polling fallback

</td>
</tr>
</table>

<p align="center"><sub><a href="docs/features.md">Every feature in detail</a></sub></p>

<p align="center"><b>Built with</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## Quick start

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

Before you migrate, add `"inertia"` and `"escalated"` to `INSTALLED_APPS` and include `escalated.urls` at `support/`. Then visit `/support`. Needs Python 3.10+ and Django 5.2+. The [getting started guide](docs/getting-started.md) has each step.

## Learn more

- [All features](docs/features.md) · [Getting started](docs/getting-started.md) · [Frontend integration and translations](docs/frontend-integration.md)
- [Configuration, hosting modes, commands, routes and signals](docs/operations.md)
- [Agent panel](docs/agent-panel.md) · [Access control](docs/access-control.md) · [Ticket access and routing](docs/ticket-access-and-routing.md)
- [Embedding the widget](docs/embedding-the-widget.md) · [Embedding the admin](docs/embedding-admin.md) · [Guest access](docs/guest-access.md)
- [Private attachments](docs/private-attachments.md) · [Plugin SDK](docs/plugin-sdk.md) · [Plugins](docs/plugins.md) · [Newsletters](docs/newsletters.md)

Escalated is also available for [Laravel](https://github.com/escalated-dev/escalated-laravel), [Rails](https://github.com/escalated-dev/escalated-rails), [NestJS](https://github.com/escalated-dev/escalated-nestjs), [AdonisJS](https://github.com/escalated-dev/escalated-adonis), [Symfony](https://github.com/escalated-dev/escalated-symfony), [Phoenix](https://github.com/escalated-dev/escalated-phoenix), [Go](https://github.com/escalated-dev/escalated-go), [.NET](https://github.com/escalated-dev/escalated-dotnet), [Spring](https://github.com/escalated-dev/escalated-spring), [WordPress](https://github.com/escalated-dev/escalated-wordpress) and [Filament](https://github.com/escalated-dev/escalated-filament). The UI lives in [escalated](https://github.com/escalated-dev/escalated).

## License

MIT. Copyright (c) 2026 Escalated.dev. See [LICENSE](LICENSE).

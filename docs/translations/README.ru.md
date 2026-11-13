<p align="center"><sub>
  <a href="README.ar.md">العربية</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="../../README.md">English</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.it.md">Italiano</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.pt-BR.md">Português (BR)</a> ·
  <b>Русский</b> ·
  <a href="README.tr.md">Türkçe</a> ·
  <a href="README.zh-CN.md">简体中文</a>
</sub></p>

<p align="center">
  <a href="https://escalated.dev"><img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/logo.png" width="72" height="72" alt="Escalated"></a>
</p>

<h1 align="center">Escalated for Django</h1>

<p align="center">
  Добавьте полноценный хелпдеск в своё приложение на Django.<br>
  Тикеты, SLA, правила эскалации, входящие для агентов и клиентский портал, и всё это в вашей собственной базе данных.
</p>

<p align="center">
  <a href="https://escalated.dev"><b>Сайт</b></a> ·
  <a href="https://escalated.dev/docs"><b>Документация</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>Список изменений</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="Входящие агента в Escalated: сохранённые представления со счётчиками, обратный отсчёт SLA и приоритеты у каждого тикета" width="100%">
</picture>

## Что он умеет

<table>
  <tr>
    <td width="40%">
      <h3>Входящие, в которых агенты могут работать весь день</h3>
      Переписка, внутренние заметки, шаблоны ответов и таймеры SLA на одном экране. Тикеты также приходят по почте через Mailgun, Postmark, SES или IMAP.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="Тикет, открытый в рабочей области агента, с редактором ответа">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="Страница отчётов в админке со временем ответа, CSAT и нарушениями SLA">
      </picture>
    </td>
    <td width="40%">
      <h3>SLA и правила эскалации у вас перед глазами</h3>
      Цели по времени ответа и решения для каждого приоритета с учётом рабочих часов, правила, которые эскалируют или переназначают тикет, когда срок срывается, и отчёты о нарушениях.
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>Готовый клиентский портал</h3>
      Клиенты создают тикеты, отвечают и проверяют статус прямо в вашем приложении. Виджет встраивается на другие сайты одним тегом script.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="Список тикетов в клиентском портале">
      </picture>
    </td>
  </tr>
</table>

## Возможности

<table>
<tr>
<td width="33%" valign="top">

**Тикеты и входящие**
- Полный жизненный цикл со сменой статусов
- Фильтры очередей и массовые действия
- Внутренние заметки и шаблоны ответов
- Выделение ответа в новый тикет
- Отложенные тикеты с пресетами и автоматическим возвратом
- Сохранённые представления и общие очереди

</td>
<td width="33%" valign="top">

**SLA и эскалация**
- Цели по ответу и решению для каждого приоритета
- Рабочие часы и обнаружение нарушений
- Правила, которые эскалируют, переназначают или уведомляют
- Маршрутизация по отделам по кругу (round-robin)

</td>
<td width="33%" valign="top">

**Клиенты**
- Клиентский портал самообслуживания
- Встраиваемый виджет с поиском по базе знаний
- Публичная база знаний, которую можно отключить

</td>
</tr>
<tr>
<td width="33%" valign="top">

**Почта**
- Входящая почта через Mailgun, Postmark, SES или IMAP
- Ответы цепочками в почтовых клиентах
- Шаблоны писем в вашем фирменном стиле
- Уведомления и вебхуки по каждому событию

</td>
<td width="33%" valign="top">

**Администрирование и доступ**
- Отделы, SLA, правила, теги и отчёты
- Роли и права как переключатель при установке
- Лента активности у каждого тикета

</td>
<td width="33%" valign="top">

**Под капотом**
- Общий интерфейс на Vue 3 и Inertia.js
- Загрузка файлов с ограничениями хранилища и размера
- Цветные теги для сортировки тикетов
- Реальное время через Django Channels с опросом в качестве запасного варианта

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">Все возможности подробно</a></sub></p>

<p align="center"><b>Построено на</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## Быстрый старт

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

Перед миграцией добавьте `"inertia"` и `"escalated"` в `INSTALLED_APPS` и подключите `escalated.urls` по пути `support/`. Затем откройте `/support`. Нужны Python 3.10+ и Django 5.2+. В [руководстве по началу работы](../getting-started.md) описан каждый шаг.

## Подробнее

- [Все возможности](../features.md) · [Начало работы](../getting-started.md) · [Интеграция фронтенда и переводы](../frontend-integration.md)
- [Настройка, режимы хостинга, команды, маршруты и сигналы](../operations.md)
- [Панель агента](../agent-panel.md) · [Управление доступом](../access-control.md) · [Доступ к тикетам и маршрутизация](../ticket-access-and-routing.md)
- [Встраивание виджета](../embedding-the-widget.md) · [Встраивание админки](../embedding-admin.md) · [Гостевой доступ](../guest-access.md)
- [Приватные вложения](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [Плагины](../plugins.md) · [Рассылки](../newsletters.md)

Escalated также доступен для [Laravel](https://github.com/escalated-dev/escalated-laravel), [Rails](https://github.com/escalated-dev/escalated-rails), [NestJS](https://github.com/escalated-dev/escalated-nestjs), [AdonisJS](https://github.com/escalated-dev/escalated-adonis), [Symfony](https://github.com/escalated-dev/escalated-symfony), [Phoenix](https://github.com/escalated-dev/escalated-phoenix), [Go](https://github.com/escalated-dev/escalated-go), [.NET](https://github.com/escalated-dev/escalated-dotnet), [Spring](https://github.com/escalated-dev/escalated-spring), [WordPress](https://github.com/escalated-dev/escalated-wordpress) и [Filament](https://github.com/escalated-dev/escalated-filament). Интерфейс находится в [escalated](https://github.com/escalated-dev/escalated).

## Лицензия

MIT. Copyright (c) 2026 Escalated.dev. См. [LICENSE](../../LICENSE).

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
  <a href="README.ru.md">Русский</a> ·
  <a href="README.tr.md">Türkçe</a> ·
  <b>简体中文</b>
</sub></p>

<p align="center">
  <a href="https://escalated.dev"><img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/logo.png" width="72" height="72" alt="Escalated"></a>
</p>

<h1 align="center">Escalated for Django</h1>

<p align="center">
  为你的 Django 应用加上一套完整的帮助台。<br>
  工单、SLA、升级规则、客服收件箱和客户门户，全部运行在你自己的数据库上。
</p>

<p align="center">
  <a href="https://escalated.dev"><b>官网</b></a> ·
  <a href="https://escalated.dev/docs"><b>文档</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>更新日志</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="Escalated 客服收件箱：带计数的已保存视图，每个工单都显示 SLA 倒计时和优先级" width="100%">
</picture>

## 它能做什么

<table>
  <tr>
    <td width="40%">
      <h3>客服可以全天使用的收件箱</h3>
      对话、内部备注、预设回复和 SLA 计时器都在同一个界面上。工单也可以通过 Mailgun、Postmark、SES 或 IMAP 以邮件形式进入。
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="在客服工作区中打开的工单和回复编辑器">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="管理后台的报表页面，显示响应时间、CSAT 和 SLA 违约">
      </picture>
    </td>
    <td width="40%">
      <h3>一目了然的 SLA 和升级规则</h3>
      按优先级设置响应和解决目标并考虑工作时间，目标即将落空时自动升级或重新分配的规则，以及违约报表。
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>现成的客户门户</h3>
      客户在你的应用里提交工单、回复并查看状态。只需一个 script 标签，就能把小部件嵌入到其他网站。
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="客户门户中的工单列表">
      </picture>
    </td>
  </tr>
</table>

## 功能

<table>
<tr>
<td width="33%" valign="top">

**工单和收件箱**
- 带状态流转的完整生命周期
- 队列筛选和批量操作
- 内部备注和预设回复
- 将一条回复拆分为新工单
- 使用预设暂缓并自动唤醒
- 已保存视图和共享队列

</td>
<td width="33%" valign="top">

**SLA 和升级**
- 按优先级设置响应和解决目标
- 工作时间和违约检测
- 可升级、重新分配或发送通知的规则
- 按部门轮询分配

</td>
<td width="33%" valign="top">

**客户**
- 自助服务客户门户
- 可嵌入的小部件，支持知识库搜索
- 可以关闭的公开知识库

</td>
</tr>
<tr>
<td width="33%" valign="top">

**邮件**
- 通过 Mailgun、Postmark、SES 或 IMAP 接收邮件
- 在邮件客户端中按会话串联回复
- 带品牌样式的邮件模板
- 按事件发送通知和 webhook

</td>
<td width="33%" valign="top">

**管理和权限**
- 部门、SLA、规则、标签和报表
- 角色和权限可在安装时开关
- 每个工单都有活动时间线

</td>
<td width="33%" valign="top">

**底层实现**
- 共享的 Vue 3 和 Inertia.js 界面
- 带存储和大小限制的文件上传
- 用彩色标签整理工单
- 基于 Django Channels 的实时更新，并以轮询作为后备

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">查看所有功能详情</a></sub></p>

<p align="center"><b>技术栈</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## 快速开始

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

迁移之前，先把 `"inertia"` 和 `"escalated"` 加入 `INSTALLED_APPS`，并在 `support/` 下引入 `escalated.urls`。然后访问 `/support`。需要 Python 3.10+ 和 Django 5.2+。[入门指南](../getting-started.md)介绍了每一个步骤。

## 了解更多

- [所有功能](../features.md) · [入门](../getting-started.md) · [前端集成和翻译](../frontend-integration.md)
- [配置、托管模式、命令、路由和信号](../operations.md)
- [客服面板](../agent-panel.md) · [访问控制](../access-control.md) · [工单访问和路由](../ticket-access-and-routing.md)
- [嵌入小部件](../embedding-the-widget.md) · [嵌入管理后台](../embedding-admin.md) · [访客访问](../guest-access.md)
- [私有附件](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [插件](../plugins.md) · [邮件简报](../newsletters.md)

Escalated 也提供 [Laravel](https://github.com/escalated-dev/escalated-laravel)、[Rails](https://github.com/escalated-dev/escalated-rails)、[NestJS](https://github.com/escalated-dev/escalated-nestjs)、[AdonisJS](https://github.com/escalated-dev/escalated-adonis)、[Symfony](https://github.com/escalated-dev/escalated-symfony)、[Phoenix](https://github.com/escalated-dev/escalated-phoenix)、[Go](https://github.com/escalated-dev/escalated-go)、[.NET](https://github.com/escalated-dev/escalated-dotnet)、[Spring](https://github.com/escalated-dev/escalated-spring)、[WordPress](https://github.com/escalated-dev/escalated-wordpress) 和 [Filament](https://github.com/escalated-dev/escalated-filament) 版本。界面代码位于 [escalated](https://github.com/escalated-dev/escalated)。

## 许可证

MIT。Copyright (c) 2026 Escalated.dev。参见 [LICENSE](../../LICENSE)。

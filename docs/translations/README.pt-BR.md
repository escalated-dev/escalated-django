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
  <b>Português (BR)</b> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.tr.md">Türkçe</a> ·
  <a href="README.zh-CN.md">简体中文</a>
</sub></p>

<p align="center">
  <a href="https://escalated.dev"><img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/logo.png" width="72" height="72" alt="Escalated"></a>
</p>

<h1 align="center">Escalated for Django</h1>

<p align="center">
  Adicione um helpdesk completo ao seu app Django.<br>
  Tickets, SLAs, regras de escalonamento, uma caixa de entrada para agentes e um portal do cliente, rodando no seu próprio banco de dados.
</p>

<p align="center">
  <a href="https://escalated.dev"><b>Site</b></a> ·
  <a href="https://escalated.dev/docs"><b>Documentação</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>Histórico de mudanças</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="A caixa de entrada de agentes do Escalated: visualizações salvas com contadores, contagens regressivas de SLA e prioridades em cada ticket" width="100%">
</picture>

## O que ele faz

<table>
  <tr>
    <td width="40%">
      <h3>Uma caixa de entrada em que seus agentes trabalham o dia todo</h3>
      Conversa, notas internas, respostas prontas e timers de SLA em uma única tela. Os tickets também chegam por e-mail via Mailgun, Postmark, SES ou IMAP.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="Um ticket aberto no espaço de trabalho do agente com o editor de resposta">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="A página de relatórios do admin com tempos de resposta, CSAT e violações de SLA">
      </picture>
    </td>
    <td width="40%">
      <h3>SLAs e regras de escalonamento que você consegue ver</h3>
      Metas de resposta e resolução por prioridade com horário comercial, regras que escalonam ou reatribuem quando uma meta escapa, e relatórios de violações.
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>Um portal do cliente que já vem pronto</h3>
      Os clientes abrem tickets, respondem e acompanham o status dentro do seu app. Incorpore o widget em outros sites com uma única tag script.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="A lista de tickets do portal do cliente">
      </picture>
    </td>
  </tr>
</table>

## Recursos

<table>
<tr>
<td width="33%" valign="top">

**Tickets e caixa de entrada**
- Ciclo de vida completo com transições de status
- Filtros de fila e ações em massa
- Notas internas e respostas prontas
- Separar uma resposta em um novo ticket
- Adiar com predefinições e reativação automática
- Visualizações salvas e filas compartilhadas

</td>
<td width="33%" valign="top">

**SLAs e escalonamento**
- Metas de resposta e resolução por prioridade
- Horário comercial e detecção de violações
- Regras que escalonam, reatribuem ou notificam
- Roteamento por departamento com round-robin

</td>
<td width="33%" valign="top">

**Clientes**
- Portal de autoatendimento para clientes
- Widget incorporável com busca na base de conhecimento
- Base de conhecimento pública que você pode desativar

</td>
</tr>
<tr>
<td width="33%" valign="top">

**E-mail**
- Entrada via Mailgun, Postmark, SES ou IMAP
- Respostas em thread nos clientes de e-mail
- Modelos de e-mail com a sua marca
- Notificações e webhooks por evento

</td>
<td width="33%" valign="top">

**Admin e acesso**
- Departamentos, SLAs, regras, tags e relatórios
- Papéis e permissões como opção da instalação
- Linha do tempo de atividades em cada ticket

</td>
<td width="33%" valign="top">

**Por baixo dos panos**
- Interface compartilhada em Vue 3 e Inertia.js
- Uploads com limites de armazenamento e tamanho
- Tags coloridas para organizar tickets
- Tempo real com Django Channels e polling como alternativa

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">Todos os recursos em detalhe</a></sub></p>

<p align="center"><b>Feito com</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## Início rápido

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

Antes de migrar, adicione `"inertia"` e `"escalated"` a `INSTALLED_APPS` e inclua `escalated.urls` em `support/`. Depois acesse `/support`. Requer Python 3.10+ e Django 5.2+. O [guia de primeiros passos](../getting-started.md) traz cada etapa.

## Saiba mais

- [Todos os recursos](../features.md) · [Primeiros passos](../getting-started.md) · [Integração do frontend e traduções](../frontend-integration.md)
- [Configuração, modos de hospedagem, comandos, rotas e signals](../operations.md)
- [Painel do agente](../agent-panel.md) · [Controle de acesso](../access-control.md) · [Acesso a tickets e roteamento](../ticket-access-and-routing.md)
- [Incorporar o widget](../embedding-the-widget.md) · [Incorporar o admin](../embedding-admin.md) · [Acesso de convidados](../guest-access.md)
- [Anexos privados](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [Plugins](../plugins.md) · [Newsletters](../newsletters.md)

O Escalated também está disponível para [Laravel](https://github.com/escalated-dev/escalated-laravel), [Rails](https://github.com/escalated-dev/escalated-rails), [NestJS](https://github.com/escalated-dev/escalated-nestjs), [AdonisJS](https://github.com/escalated-dev/escalated-adonis), [Symfony](https://github.com/escalated-dev/escalated-symfony), [Phoenix](https://github.com/escalated-dev/escalated-phoenix), [Go](https://github.com/escalated-dev/escalated-go), [.NET](https://github.com/escalated-dev/escalated-dotnet), [Spring](https://github.com/escalated-dev/escalated-spring), [WordPress](https://github.com/escalated-dev/escalated-wordpress) e [Filament](https://github.com/escalated-dev/escalated-filament). A interface fica em [escalated](https://github.com/escalated-dev/escalated).

## Licença

MIT. Copyright (c) 2026 Escalated.dev. Veja [LICENSE](../../LICENSE).

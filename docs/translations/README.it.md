<p align="center"><sub>
  <a href="README.ar.md">العربية</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="../../README.md">English</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <b>Italiano</b> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.pt-BR.md">Português (BR)</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.tr.md">Türkçe</a> ·
  <a href="README.zh-CN.md">简体中文</a>
</sub></p>

<p align="center">
  <a href="https://escalated.dev"><img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/logo.png" width="72" height="72" alt="Escalated"></a>
</p>

<h1 align="center">Escalated for Django</h1>

<p align="center">
  Aggiungi un helpdesk completo alla tua app Django.<br>
  Ticket, SLA, regole di escalation, una inbox per gli agenti e un portale clienti, sul tuo database.
</p>

<p align="center">
  <a href="https://escalated.dev"><b>Sito web</b></a> ·
  <a href="https://escalated.dev/docs"><b>Documentazione</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>Registro delle modifiche</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="La inbox degli agenti di Escalated: viste salvate con contatori, conti alla rovescia SLA e priorità su ogni ticket" width="100%">
</picture>

## Cosa fa

<table>
  <tr>
    <td width="40%">
      <h3>Una inbox in cui i tuoi agenti possono lavorare tutto il giorno</h3>
      Conversazione, note interne, risposte predefinite e timer SLA in un'unica schermata. I ticket arrivano anche via email tramite Mailgun, Postmark, SES o IMAP.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="Un ticket aperto nell'area di lavoro dell'agente con l'editor di risposta">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="La pagina dei report di amministrazione con tempi di risposta, CSAT e violazioni degli SLA">
      </picture>
    </td>
    <td width="40%">
      <h3>SLA e regole di escalation sempre sotto controllo</h3>
      Obiettivi di risposta e risoluzione per priorità con orari lavorativi, regole che fanno escalation o riassegnano quando un obiettivo slitta, e report sulle violazioni.
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>Un portale clienti già pronto</h3>
      I clienti aprono ticket, rispondono e controllano lo stato dentro la tua app. Incorpora il widget su altri siti con un solo tag script.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="L'elenco dei ticket nel portale clienti">
      </picture>
    </td>
  </tr>
</table>

## Funzionalità

<table>
<tr>
<td width="33%" valign="top">

**Ticket e inbox**
- Ciclo di vita completo con transizioni di stato
- Filtri per coda e azioni di massa
- Note interne e risposte predefinite
- Separare una risposta in un nuovo ticket
- Posticipa con preimpostazioni e riattivazione automatica
- Viste salvate e code condivise

</td>
<td width="33%" valign="top">

**SLA ed escalation**
- Obiettivi di risposta e risoluzione per priorità
- Orari lavorativi e rilevamento delle violazioni
- Regole che fanno escalation, riassegnano o notificano
- Instradamento per reparto con round-robin

</td>
<td width="33%" valign="top">

**Clienti**
- Portale clienti self-service
- Widget incorporabile con ricerca nella knowledge base
- Knowledge base pubblica che puoi disattivare

</td>
</tr>
<tr>
<td width="33%" valign="top">

**Email**
- In ingresso tramite Mailgun, Postmark, SES o IMAP
- Risposte raggruppate in thread nei client di posta
- Template email con il tuo brand
- Notifiche e webhook per evento

</td>
<td width="33%" valign="top">

**Amministrazione e accesso**
- Reparti, SLA, regole, tag e report
- Ruoli e permessi attivabili all'installazione
- Cronologia delle attività su ogni ticket

</td>
<td width="33%" valign="top">

**Sotto il cofano**
- Interfaccia condivisa con Vue 3 e Inertia.js
- Upload con limiti di archiviazione e dimensione
- Tag colorati per ordinare i ticket
- Tempo reale con Django Channels e polling come ripiego

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">Tutte le funzionalità nel dettaglio</a></sub></p>

<p align="center"><b>Realizzato con</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## Avvio rapido

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

Prima di eseguire la migrazione, aggiungi `"inertia"` ed `"escalated"` a `INSTALLED_APPS` e includi `escalated.urls` su `support/`. Poi apri `/support`. Richiede Python 3.10+ e Django 5.2+. La [guida introduttiva](../getting-started.md) spiega ogni passaggio.

## Per saperne di più

- [Tutte le funzionalità](../features.md) · [Per iniziare](../getting-started.md) · [Integrazione frontend e traduzioni](../frontend-integration.md)
- [Configurazione, modalità di hosting, comandi, route e segnali](../operations.md)
- [Pannello agente](../agent-panel.md) · [Controllo degli accessi](../access-control.md) · [Accesso ai ticket e instradamento](../ticket-access-and-routing.md)
- [Incorporare il widget](../embedding-the-widget.md) · [Incorporare l'amministrazione](../embedding-admin.md) · [Accesso ospite](../guest-access.md)
- [Allegati privati](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [Plugin](../plugins.md) · [Newsletter](../newsletters.md)

Escalated è disponibile anche per [Laravel](https://github.com/escalated-dev/escalated-laravel), [Rails](https://github.com/escalated-dev/escalated-rails), [NestJS](https://github.com/escalated-dev/escalated-nestjs), [AdonisJS](https://github.com/escalated-dev/escalated-adonis), [Symfony](https://github.com/escalated-dev/escalated-symfony), [Phoenix](https://github.com/escalated-dev/escalated-phoenix), [Go](https://github.com/escalated-dev/escalated-go), [.NET](https://github.com/escalated-dev/escalated-dotnet), [Spring](https://github.com/escalated-dev/escalated-spring), [WordPress](https://github.com/escalated-dev/escalated-wordpress) e [Filament](https://github.com/escalated-dev/escalated-filament). L'interfaccia si trova in [escalated](https://github.com/escalated-dev/escalated).

## Licenza

MIT. Copyright (c) 2026 Escalated.dev. Vedi [LICENSE](../../LICENSE).

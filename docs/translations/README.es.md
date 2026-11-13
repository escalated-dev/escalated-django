<p align="center"><sub>
  <a href="README.ar.md">العربية</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="../../README.md">English</a> ·
  <b>Español</b> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.it.md">Italiano</a> ·
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
  Añade un helpdesk completo a tu app de Django.<br>
  Tickets, SLAs, reglas de escalado, una bandeja de entrada para agentes y un portal de clientes, sobre tu propia base de datos.
</p>

<p align="center">
  <a href="https://escalated.dev"><b>Sitio web</b></a> ·
  <a href="https://escalated.dev/docs"><b>Documentación</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>Registro de cambios</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="La bandeja de entrada de agentes de Escalated: vistas guardadas con contadores, cuentas atrás de SLA y prioridades en cada ticket" width="100%">
</picture>

## Qué hace

<table>
  <tr>
    <td width="40%">
      <h3>Una bandeja de entrada en la que tus agentes pueden trabajar todo el día</h3>
      Conversación, notas internas, respuestas predefinidas y temporizadores de SLA en una sola pantalla. Los tickets también llegan por correo a través de Mailgun, Postmark, SES o IMAP.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="Un ticket abierto en el espacio de trabajo del agente con el editor de respuestas">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="La página de informes de administración con tiempos de respuesta, CSAT e incumplimientos de SLA">
      </picture>
    </td>
    <td width="40%">
      <h3>SLAs y reglas de escalado que puedes ver</h3>
      Objetivos de respuesta y resolución por prioridad con horario laboral, reglas que escalan o reasignan cuando se incumplen, e informes sobre los incumplimientos.
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>Un portal de clientes que ya está hecho</h3>
      Los clientes abren tickets, responden y consultan el estado dentro de tu app. Inserta el widget en otros sitios con una sola etiqueta de script.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="La lista de tickets del portal de clientes">
      </picture>
    </td>
  </tr>
</table>

## Funciones

<table>
<tr>
<td width="33%" valign="top">

**Tickets y bandeja de entrada**
- Ciclo de vida completo con transiciones de estado
- Filtros de cola y acciones masivas
- Notas internas y respuestas predefinidas
- Separar una respuesta en un ticket nuevo
- Posponer con valores predefinidos y reactivación automática
- Vistas guardadas y colas compartidas

</td>
<td width="33%" valign="top">

**SLAs y escalado**
- Objetivos de respuesta y resolución por prioridad
- Horario laboral y detección de incumplimientos
- Reglas que escalan, reasignan o notifican
- Enrutamiento por departamento con round-robin

</td>
<td width="33%" valign="top">

**Clientes**
- Portal de autoservicio para clientes
- Widget insertable con búsqueda en la base de conocimiento
- Base de conocimiento pública que puedes desactivar

</td>
</tr>
<tr>
<td width="33%" valign="top">

**Correo**
- Entrada a través de Mailgun, Postmark, SES o IMAP
- Respuestas agrupadas en hilos en los clientes de correo
- Plantillas de correo con tu marca
- Notificaciones y webhooks por evento

</td>
<td width="33%" valign="top">

**Administración y acceso**
- Departamentos, SLAs, reglas, etiquetas e informes
- Roles y permisos como opción de instalación
- Historial de actividad en cada ticket

</td>
<td width="33%" valign="top">

**Por dentro**
- Interfaz compartida con Vue 3 e Inertia.js
- Subidas con límites de almacenamiento y tamaño
- Etiquetas de colores para ordenar tickets
- Tiempo real con Django Channels y polling como respaldo

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">Todas las funciones en detalle</a></sub></p>

<p align="center"><b>Hecho con</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## Inicio rápido

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

Antes de migrar, añade `"inertia"` y `"escalated"` a `INSTALLED_APPS` e incluye `escalated.urls` en `support/`. Después visita `/support`. Requiere Python 3.10+ y Django 5.2+. La [guía de primeros pasos](../getting-started.md) explica cada paso.

## Más información

- [Todas las funciones](../features.md) · [Primeros pasos](../getting-started.md) · [Integración del frontend y traducciones](../frontend-integration.md)
- [Configuración, modos de alojamiento, comandos, rutas y señales](../operations.md)
- [Panel del agente](../agent-panel.md) · [Control de acceso](../access-control.md) · [Acceso a tickets y enrutamiento](../ticket-access-and-routing.md)
- [Insertar el widget](../embedding-the-widget.md) · [Insertar la administración](../embedding-admin.md) · [Acceso de invitados](../guest-access.md)
- [Adjuntos privados](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [Plugins](../plugins.md) · [Boletines](../newsletters.md)

Escalated también está disponible para [Laravel](https://github.com/escalated-dev/escalated-laravel), [Rails](https://github.com/escalated-dev/escalated-rails), [NestJS](https://github.com/escalated-dev/escalated-nestjs), [AdonisJS](https://github.com/escalated-dev/escalated-adonis), [Symfony](https://github.com/escalated-dev/escalated-symfony), [Phoenix](https://github.com/escalated-dev/escalated-phoenix), [Go](https://github.com/escalated-dev/escalated-go), [.NET](https://github.com/escalated-dev/escalated-dotnet), [Spring](https://github.com/escalated-dev/escalated-spring), [WordPress](https://github.com/escalated-dev/escalated-wordpress) y [Filament](https://github.com/escalated-dev/escalated-filament). La interfaz está en [escalated](https://github.com/escalated-dev/escalated).

## Licencia

MIT. Copyright (c) 2026 Escalated.dev. Consulta [LICENSE](../../LICENSE).

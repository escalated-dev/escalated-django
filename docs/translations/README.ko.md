<p align="center"><sub>
  <a href="README.ar.md">العربية</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="../../README.md">English</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.it.md">Italiano</a> ·
  <a href="README.ja.md">日本語</a> ·
  <b>한국어</b> ·
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
  Django 앱에 완전한 헬프데스크를 추가하세요.<br>
  티켓, SLA, 에스컬레이션 규칙, 상담원 받은편지함, 고객 포털이 여러분의 데이터베이스에서 그대로 동작합니다.
</p>

<p align="center">
  <a href="https://escalated.dev"><b>웹사이트</b></a> ·
  <a href="https://escalated.dev/docs"><b>문서</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>변경 내역</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="Escalated 상담원 받은편지함: 개수가 표시된 저장된 보기, SLA 카운트다운, 모든 티켓의 우선순위" width="100%">
</picture>

## 할 수 있는 일

<table>
  <tr>
    <td width="40%">
      <h3>상담원이 하루 종일 일할 수 있는 받은편지함</h3>
      대화, 내부 메모, 정형 답변, SLA 타이머를 한 화면에서 다룹니다. 티켓은 Mailgun, Postmark, SES 또는 IMAP을 통해 이메일로도 들어옵니다.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="답장 편집기가 있는 상담원 작업 공간에서 연 티켓">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="응답 시간, CSAT, SLA 위반을 보여 주는 관리자 보고서 페이지">
      </picture>
    </td>
    <td width="40%">
      <h3>한눈에 보이는 SLA와 에스컬레이션 규칙</h3>
      영업시간을 반영한 우선순위별 응답 및 해결 목표, 목표를 놓치면 에스컬레이션하거나 재배정하는 규칙, 위반 보고서를 제공합니다.
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>이미 만들어진 고객 포털</h3>
      고객은 여러분의 앱 안에서 티켓을 열고, 답장하고, 상태를 확인합니다. script 태그 하나로 다른 사이트에 위젯을 삽입할 수 있습니다.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="고객 포털의 티켓 목록">
      </picture>
    </td>
  </tr>
</table>

## 기능

<table>
<tr>
<td width="33%" valign="top">

**티켓과 받은편지함**
- 상태 전환을 포함한 전체 수명 주기
- 대기열 필터와 일괄 작업
- 내부 메모와 정형 답변
- 답장을 새 티켓으로 분리
- 프리셋과 자동 재개를 지원하는 다시 알림
- 저장된 보기와 공유 대기열

</td>
<td width="33%" valign="top">

**SLA와 에스컬레이션**
- 우선순위별 응답 및 해결 목표
- 영업시간과 위반 감지
- 에스컬레이션, 재배정, 알림을 수행하는 규칙
- 라운드 로빈 방식의 부서별 라우팅

</td>
<td width="33%" valign="top">

**고객**
- 셀프서비스 고객 포털
- 지식 베이스 검색이 포함된 삽입형 위젯
- 끌 수 있는 공개 지식 베이스

</td>
</tr>
<tr>
<td width="33%" valign="top">

**이메일**
- Mailgun, Postmark, SES 또는 IMAP을 통한 수신
- 메일 클라이언트에서 스레드로 묶이는 답장
- 브랜드에 맞춘 이메일 템플릿
- 이벤트별 알림과 웹훅

</td>
<td width="33%" valign="top">

**관리와 접근 권한**
- 부서, SLA, 규칙, 태그, 보고서
- 설치 시 켜고 끌 수 있는 역할과 권한
- 모든 티켓의 활동 기록

</td>
<td width="33%" valign="top">

**내부 구조**
- Vue 3와 Inertia.js로 만든 공용 UI
- 저장소 및 크기 제한이 있는 업로드
- 티켓 정리를 위한 색상 태그
- 폴링으로 대체되는 Django Channels 실시간 업데이트

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">모든 기능 자세히 보기</a></sub></p>

<p align="center"><b>사용 기술</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## 빠른 시작

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

마이그레이션하기 전에 `"inertia"`와 `"escalated"`를 `INSTALLED_APPS`에 추가하고 `escalated.urls`를 `support/`에 포함하세요. 그다음 `/support`에 접속합니다. Python 3.10 이상과 Django 5.2 이상이 필요합니다. 각 단계는 [시작 가이드](../getting-started.md)에 나와 있습니다.

## 더 알아보기

- [모든 기능](../features.md) · [시작하기](../getting-started.md) · [프런트엔드 통합과 번역](../frontend-integration.md)
- [설정, 호스팅 모드, 명령, 라우트, 시그널](../operations.md)
- [상담원 패널](../agent-panel.md) · [접근 제어](../access-control.md) · [티켓 접근과 라우팅](../ticket-access-and-routing.md)
- [위젯 삽입](../embedding-the-widget.md) · [관리자 화면 삽입](../embedding-admin.md) · [게스트 접근](../guest-access.md)
- [비공개 첨부 파일](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [플러그인](../plugins.md) · [뉴스레터](../newsletters.md)

Escalated는 [Laravel](https://github.com/escalated-dev/escalated-laravel), [Rails](https://github.com/escalated-dev/escalated-rails), [NestJS](https://github.com/escalated-dev/escalated-nestjs), [AdonisJS](https://github.com/escalated-dev/escalated-adonis), [Symfony](https://github.com/escalated-dev/escalated-symfony), [Phoenix](https://github.com/escalated-dev/escalated-phoenix), [Go](https://github.com/escalated-dev/escalated-go), [.NET](https://github.com/escalated-dev/escalated-dotnet), [Spring](https://github.com/escalated-dev/escalated-spring), [WordPress](https://github.com/escalated-dev/escalated-wordpress), [Filament](https://github.com/escalated-dev/escalated-filament)용으로도 제공됩니다. UI는 [escalated](https://github.com/escalated-dev/escalated)에 있습니다.

## 라이선스

MIT. Copyright (c) 2026 Escalated.dev. [LICENSE](../../LICENSE)를 참고하세요.

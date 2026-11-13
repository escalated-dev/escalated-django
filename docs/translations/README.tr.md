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
  <b>Türkçe</b> ·
  <a href="README.zh-CN.md">简体中文</a>
</sub></p>

<p align="center">
  <a href="https://escalated.dev"><img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/logo.png" width="72" height="72" alt="Escalated"></a>
</p>

<h1 align="center">Escalated for Django</h1>

<p align="center">
  Django uygulamana eksiksiz bir yardım masası ekle.<br>
  Talepler, SLA'lar, eskalasyon kuralları, temsilci gelen kutusu ve müşteri portalı, hepsi kendi veritabanında çalışır.
</p>

<p align="center">
  <a href="https://escalated.dev"><b>Web sitesi</b></a> ·
  <a href="https://escalated.dev/docs"><b>Dokümantasyon</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>Değişiklik günlüğü</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="Escalated temsilci gelen kutusu: sayaçlı kayıtlı görünümler, her talepte SLA geri sayımları ve öncelikler" width="100%">
</picture>

## Ne yapar

<table>
  <tr>
    <td width="40%">
      <h3>Temsilcilerinin bütün gün çalışabileceği bir gelen kutusu</h3>
      Konuşma, dahili notlar, hazır yanıtlar ve SLA sayaçları tek ekranda. Talepler Mailgun, Postmark, SES veya IMAP üzerinden e-postayla da gelir.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="Temsilci çalışma alanında yanıt düzenleyicisiyle açık bir talep">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="Yanıt süreleri, CSAT ve SLA ihlallerini gösteren yönetici rapor sayfası">
      </picture>
    </td>
    <td width="40%">
      <h3>Görebildiğin SLA'lar ve eskalasyon kuralları</h3>
      Mesai saatlerini hesaba katan, önceliğe göre yanıt ve çözüm hedefleri, bir hedef kaçtığında eskale eden veya yeniden atayan kurallar ve ihlal raporları.
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>Hazır gelen bir müşteri portalı</h3>
      Müşteriler uygulamanın içinde talep açar, yanıt verir ve durumu takip eder. Widget'ı tek bir script etiketiyle başka sitelere yerleştirebilirsin.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="Müşteri portalındaki talep listesi">
      </picture>
    </td>
  </tr>
</table>

## Özellikler

<table>
<tr>
<td width="33%" valign="top">

**Talepler ve gelen kutusu**
- Durum geçişleriyle tam yaşam döngüsü
- Kuyruk filtreleri ve toplu işlemler
- Dahili notlar ve hazır yanıtlar
- Bir yanıtı yeni bir talebe ayırma
- Hazır ayarlarla erteleme ve otomatik uyandırma
- Kayıtlı görünümler ve paylaşılan kuyruklar

</td>
<td width="33%" valign="top">

**SLA'lar ve eskalasyon**
- Önceliğe göre yanıt ve çözüm hedefleri
- Mesai saatleri ve ihlal tespiti
- Eskale eden, yeniden atayan veya bildirim gönderen kurallar
- Round-robin ile departman yönlendirmesi

</td>
<td width="33%" valign="top">

**Müşteriler**
- Self servis müşteri portalı
- Bilgi bankası aramalı yerleştirilebilir widget
- Kapatabileceğin herkese açık bilgi bankası

</td>
</tr>
<tr>
<td width="33%" valign="top">

**E-posta**
- Mailgun, Postmark, SES veya IMAP ile gelen e-posta
- E-posta istemcilerinde zincirli yanıtlar
- Markana uygun e-posta şablonları
- Olay bazında bildirimler ve webhook'lar

</td>
<td width="33%" valign="top">

**Yönetim ve erişim**
- Departmanlar, SLA'lar, kurallar, etiketler ve raporlar
- Kurulum seçeneği olarak roller ve izinler
- Her talepte etkinlik zaman çizelgesi

</td>
<td width="33%" valign="top">

**Arka planda**
- Paylaşılan Vue 3 ve Inertia.js arayüzü
- Depolama ve boyut sınırlı dosya yüklemeleri
- Talepleri düzenlemek için renkli etiketler
- Yedek olarak polling ile Django Channels üzerinden gerçek zamanlı güncellemeler

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">Tüm özellikler ayrıntılı olarak</a></sub></p>

<p align="center"><b>Kullanılan teknolojiler</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## Hızlı başlangıç

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

Migrate etmeden önce `"inertia"` ve `"escalated"` uygulamalarını `INSTALLED_APPS` listesine ekle ve `escalated.urls` adresini `support/` altına bağla. Ardından `/support` adresini aç. Python 3.10+ ve Django 5.2+ gerekir. [Başlangıç kılavuzu](../getting-started.md) her adımı anlatır.

## Daha fazla bilgi

- [Tüm özellikler](../features.md) · [Başlarken](../getting-started.md) · [Frontend entegrasyonu ve çeviriler](../frontend-integration.md)
- [Yapılandırma, barındırma modları, komutlar, rotalar ve sinyaller](../operations.md)
- [Temsilci paneli](../agent-panel.md) · [Erişim kontrolü](../access-control.md) · [Talep erişimi ve yönlendirme](../ticket-access-and-routing.md)
- [Widget'ı yerleştirme](../embedding-the-widget.md) · [Yönetim panelini yerleştirme](../embedding-admin.md) · [Misafir erişimi](../guest-access.md)
- [Özel ekler](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [Eklentiler](../plugins.md) · [Bültenler](../newsletters.md)

Escalated ayrıca [Laravel](https://github.com/escalated-dev/escalated-laravel), [Rails](https://github.com/escalated-dev/escalated-rails), [NestJS](https://github.com/escalated-dev/escalated-nestjs), [AdonisJS](https://github.com/escalated-dev/escalated-adonis), [Symfony](https://github.com/escalated-dev/escalated-symfony), [Phoenix](https://github.com/escalated-dev/escalated-phoenix), [Go](https://github.com/escalated-dev/escalated-go), [.NET](https://github.com/escalated-dev/escalated-dotnet), [Spring](https://github.com/escalated-dev/escalated-spring), [WordPress](https://github.com/escalated-dev/escalated-wordpress) ve [Filament](https://github.com/escalated-dev/escalated-filament) için de mevcut. Arayüz [escalated](https://github.com/escalated-dev/escalated) deposunda bulunur.

## Lisans

MIT. Copyright (c) 2026 Escalated.dev. Bkz. [LICENSE](../../LICENSE).

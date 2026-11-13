<p align="center"><sub>
  <b>العربية</b> ·
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
  <a href="README.zh-CN.md">简体中文</a>
</sub></p>

<p align="center">
  <a href="https://escalated.dev"><img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/logo.png" width="72" height="72" alt="Escalated"></a>
</p>

<h1 align="center">Escalated for Django</h1>

<p align="center">
  أضف نظام دعم فني متكاملًا إلى تطبيق Django الخاص بك.<br>
  التذاكر واتفاقيات مستوى الخدمة (SLA) وقواعد التصعيد وصندوق وارد للوكلاء وبوابة للعملاء، كلها تعمل على قاعدة بياناتك.
</p>

<p align="center">
  <a href="https://escalated.dev"><b>الموقع</b></a> ·
  <a href="https://escalated.dev/docs"><b>التوثيق</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>سجل التغييرات</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="صندوق وارد الوكلاء في Escalated: عروض محفوظة مع أعداد، وعدّادات تنازلية لـ SLA، وأولويات على كل تذكرة" width="100%">
</picture>

## ماذا يفعل

<table>
  <tr>
    <td width="40%">
      <h3>صندوق وارد يستطيع وكلاؤك العمل فيه طوال اليوم</h3>
      المحادثة والملاحظات الداخلية والردود الجاهزة ومؤقتات SLA في شاشة واحدة. تصل التذاكر أيضًا عبر البريد الإلكتروني من خلال Mailgun أو Postmark أو SES أو IMAP.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="تذكرة مفتوحة في مساحة عمل الوكيل مع محرر الرد">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="صفحة التقارير في لوحة الإدارة مع أوقات الاستجابة وCSAT وانتهاكات SLA">
      </picture>
    </td>
    <td width="40%">
      <h3>اتفاقيات SLA وقواعد تصعيد واضحة أمامك</h3>
      أهداف الاستجابة والحل لكل أولوية مع ساعات العمل، وقواعد تصعّد التذكرة أو تعيد إسنادها عند التأخر، وتقارير عن الانتهاكات.
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>بوابة عملاء جاهزة</h3>
      يفتح العملاء التذاكر ويردّون ويتابعون حالتها داخل تطبيقك. يمكنك تضمين الأداة في مواقع أخرى بوسم script واحد.
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="قائمة التذاكر في بوابة العملاء">
      </picture>
    </td>
  </tr>
</table>

## الميزات

<table>
<tr>
<td width="33%" valign="top">

**التذاكر وصندوق الوارد**
- دورة حياة كاملة مع انتقالات الحالة
- مرشحات قوائم الانتظار والإجراءات الجماعية
- ملاحظات داخلية وردود جاهزة
- فصل رد إلى تذكرة جديدة
- تأجيل مع إعدادات مسبقة وتنبيه تلقائي
- عروض محفوظة وقوائم انتظار مشتركة

</td>
<td width="33%" valign="top">

**اتفاقيات SLA والتصعيد**
- أهداف الاستجابة والحل لكل أولوية
- ساعات العمل واكتشاف الانتهاكات
- قواعد تصعّد أو تعيد الإسناد أو ترسل إشعارًا
- توجيه حسب القسم بالتناوب (round-robin)

</td>
<td width="33%" valign="top">

**العملاء**
- بوابة خدمة ذاتية للعملاء
- أداة قابلة للتضمين مع بحث في قاعدة المعرفة
- قاعدة معرفة عامة يمكنك إيقافها

</td>
</tr>
<tr>
<td width="33%" valign="top">

**البريد الإلكتروني**
- استقبال عبر Mailgun أو Postmark أو SES أو IMAP
- ردود مجمّعة في سلاسل داخل برامج البريد
- قوالب بريد بهوية علامتك التجارية
- إشعارات وwebhooks لكل حدث

</td>
<td width="33%" valign="top">

**الإدارة والصلاحيات**
- الأقسام وSLA والقواعد والوسوم والتقارير
- الأدوار والصلاحيات كخيار عند التثبيت
- سجل النشاط على كل تذكرة

</td>
<td width="33%" valign="top">

**تحت الغطاء**
- واجهة مشتركة مبنية بـ Vue 3 وInertia.js
- رفع الملفات مع حدود للتخزين والحجم
- وسوم ملونة لفرز التذاكر
- تحديث فوري عبر Django Channels مع الاستطلاع الدوري كبديل

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">كل الميزات بالتفصيل</a></sub></p>

<p align="center"><b>مبني باستخدام</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## البدء السريع

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

قبل تشغيل الترحيل، أضف `"inertia"` و`"escalated"` إلى `INSTALLED_APPS` وضمّن `escalated.urls` تحت `support/`. ثم افتح `/support`. يتطلب Python 3.10+ وDjango 5.2+. يشرح [دليل البدء](../getting-started.md) كل خطوة.

## اعرف المزيد

- [كل الميزات](../features.md) · [البدء](../getting-started.md) · [تكامل الواجهة الأمامية والترجمات](../frontend-integration.md)
- [الإعدادات وأوضاع الاستضافة والأوامر والمسارات والإشارات](../operations.md)
- [لوحة الوكيل](../agent-panel.md) · [التحكم في الوصول](../access-control.md) · [الوصول إلى التذاكر والتوجيه](../ticket-access-and-routing.md)
- [تضمين الأداة](../embedding-the-widget.md) · [تضمين لوحة الإدارة](../embedding-admin.md) · [وصول الضيوف](../guest-access.md)
- [المرفقات الخاصة](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [الإضافات](../plugins.md) · [النشرات البريدية](../newsletters.md)

يتوفر Escalated أيضًا لـ [Laravel](https://github.com/escalated-dev/escalated-laravel) و[Rails](https://github.com/escalated-dev/escalated-rails) و[NestJS](https://github.com/escalated-dev/escalated-nestjs) و[AdonisJS](https://github.com/escalated-dev/escalated-adonis) و[Symfony](https://github.com/escalated-dev/escalated-symfony) و[Phoenix](https://github.com/escalated-dev/escalated-phoenix) و[Go](https://github.com/escalated-dev/escalated-go) و[.NET](https://github.com/escalated-dev/escalated-dotnet) و[Spring](https://github.com/escalated-dev/escalated-spring) و[WordPress](https://github.com/escalated-dev/escalated-wordpress) و[Filament](https://github.com/escalated-dev/escalated-filament). توجد الواجهة في [escalated](https://github.com/escalated-dev/escalated).

## الترخيص

MIT. حقوق النشر (c) 2026 Escalated.dev. راجع [LICENSE](../../LICENSE).

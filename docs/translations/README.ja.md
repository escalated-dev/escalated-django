<p align="center"><sub>
  <a href="README.ar.md">العربية</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="../../README.md">English</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.it.md">Italiano</a> ·
  <b>日本語</b> ·
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
  Django アプリに本格的なヘルプデスクを追加できます。<br>
  チケット、SLA、エスカレーションルール、エージェント用受信トレイ、顧客ポータルが、あなた自身のデータベース上で動きます。
</p>

<p align="center">
  <a href="https://escalated.dev"><b>ウェブサイト</b></a> ·
  <a href="https://escalated.dev/docs"><b>ドキュメント</b></a> ·
  <a href="https://escalated.dev/cloud"><b>Cloud</b></a> ·
  <a href="../../CHANGELOG.md"><b>変更履歴</b></a>
</p>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-dark.png">
  <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/inbox-light.png" alt="Escalated のエージェント用受信トレイ: 件数付きの保存済みビュー、SLA のカウントダウン、各チケットの優先度" width="100%">
</picture>

## できること

<table>
  <tr>
    <td width="40%">
      <h3>エージェントが一日中作業できる受信トレイ</h3>
      会話、社内メモ、定型返信、SLA タイマーを一つの画面で扱えます。チケットは Mailgun、Postmark、SES、IMAP を通じてメールでも届きます。
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/ticket-light.png" alt="返信エディタ付きのエージェント作業画面で開いたチケット">
      </picture>
    </td>
  </tr>
  <tr>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/dashboard-light.png" alt="応答時間、CSAT、SLA 違反を表示する管理画面のレポートページ">
      </picture>
    </td>
    <td width="40%">
      <h3>状況がひと目でわかる SLA とエスカレーションルール</h3>
      営業時間を考慮した優先度ごとの応答・解決目標、目標を外れたときにエスカレーションや再割り当てを行うルール、違反に関するレポートを備えています。
    </td>
  </tr>
  <tr>
    <td width="40%">
      <h3>すぐに使える顧客ポータル</h3>
      顧客はあなたのアプリの中でチケットを作成し、返信し、状況を確認できます。script タグ一つでウィジェットを他のサイトに埋め込めます。
    </td>
    <td width="60%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-dark.png">
        <img src="https://raw.githubusercontent.com/escalated-dev/escalated/main/docs/assets/readme/portal-light.png" alt="顧客ポータルのチケット一覧">
      </picture>
    </td>
  </tr>
</table>

## 機能

<table>
<tr>
<td width="33%" valign="top">

**チケットと受信トレイ**
- ステータス遷移を含む完全なライフサイクル
- キューのフィルタと一括操作
- 社内メモと定型返信
- 返信を新しいチケットに分割
- プリセット付きのスヌーズと自動再開
- 保存済みビューと共有キュー

</td>
<td width="33%" valign="top">

**SLA とエスカレーション**
- 優先度ごとの応答・解決目標
- 営業時間と違反の検出
- エスカレーション、再割り当て、通知を行うルール
- ラウンドロビンによる部署ごとの振り分け

</td>
<td width="33%" valign="top">

**顧客**
- セルフサービスの顧客ポータル
- ナレッジベース検索付きの埋め込みウィジェット
- オフにもできる公開ナレッジベース

</td>
</tr>
<tr>
<td width="33%" valign="top">

**メール**
- Mailgun、Postmark、SES、IMAP 経由の受信
- メールクライアントでスレッド表示される返信
- ブランドに合わせたメールテンプレート
- イベントごとの通知と Webhook

</td>
<td width="33%" valign="top">

**管理とアクセス**
- 部署、SLA、ルール、タグ、レポート
- インストール時に切り替えられるロールと権限
- 各チケットのアクティビティ履歴

</td>
<td width="33%" valign="top">

**内部の仕組み**
- Vue 3 と Inertia.js による共通 UI
- ストレージとサイズ制限付きのアップロード
- チケットを整理するための色付きタグ
- Django Channels によるリアルタイム更新とポーリングへのフォールバック

</td>
</tr>
</table>

<p align="center"><sub><a href="../features.md">すべての機能の詳細</a></sub></p>

<p align="center"><b>使用技術</b></p>

<p align="center">
  <a href="https://www.djangoproject.com"><img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org"><img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue.js"></a>
  <a href="https://inertiajs.com"><img src="https://img.shields.io/badge/Inertia-9553E9?style=for-the-badge&logo=inertia&logoColor=white" alt="Inertia"></a>
</p>

## クイックスタート

```bash
pip install escalated-django
npm install @escalated-dev/escalated
python manage.py migrate escalated
```

マイグレーションの前に、`"inertia"` と `"escalated"` を `INSTALLED_APPS` に追加し、`escalated.urls` を `support/` に含めてください。その後 `/support` を開きます。Python 3.10 以上と Django 5.2 以上が必要です。各手順は[導入ガイド](../getting-started.md)で説明しています。

## 詳しく知る

- [すべての機能](../features.md) · [はじめに](../getting-started.md) · [フロントエンドの統合と翻訳](../frontend-integration.md)
- [設定、ホスティングモード、コマンド、ルート、シグナル](../operations.md)
- [エージェントパネル](../agent-panel.md) · [アクセス制御](../access-control.md) · [チケットへのアクセスと振り分け](../ticket-access-and-routing.md)
- [ウィジェットの埋め込み](../embedding-the-widget.md) · [管理画面の埋め込み](../embedding-admin.md) · [ゲストアクセス](../guest-access.md)
- [非公開の添付ファイル](../private-attachments.md) · [Plugin SDK](../plugin-sdk.md) · [プラグイン](../plugins.md) · [ニュースレター](../newsletters.md)

Escalated は [Laravel](https://github.com/escalated-dev/escalated-laravel)、[Rails](https://github.com/escalated-dev/escalated-rails)、[NestJS](https://github.com/escalated-dev/escalated-nestjs)、[AdonisJS](https://github.com/escalated-dev/escalated-adonis)、[Symfony](https://github.com/escalated-dev/escalated-symfony)、[Phoenix](https://github.com/escalated-dev/escalated-phoenix)、[Go](https://github.com/escalated-dev/escalated-go)、[.NET](https://github.com/escalated-dev/escalated-dotnet)、[Spring](https://github.com/escalated-dev/escalated-spring)、[WordPress](https://github.com/escalated-dev/escalated-wordpress)、[Filament](https://github.com/escalated-dev/escalated-filament) 向けにも提供されています。UI は [escalated](https://github.com/escalated-dev/escalated) にあります。

## ライセンス

MIT。Copyright (c) 2026 Escalated.dev。詳しくは [LICENSE](../../LICENSE) を参照してください。

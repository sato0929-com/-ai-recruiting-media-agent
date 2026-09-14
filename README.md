# 採用AIメディア自動化基盤

採用担当者・中小企業経営者向けの「採用改善とAI活用メディア」を、週1回30〜60分の確認・承認だけで運用するための自動化基盤です。

- 企画・原稿レビューなど「人が判断する作業」は **Claude Pro**(claude.ai)で行います。追加費用は発生しません。
- リサーチ・下書き・校閲一次チェックなど「無人実行する作業」だけ **Anthropic API** を使います。月間上限は既定で3,000円です。
- 投稿は **Instagram Graph API** と **YouTube Data API** の2チャネルから開始します。TikTok・WordPress・LINE連携は今は実装しません。
- 自動フォロー・自動いいね・自動コメント・自動DMは実装しません。承認ステータスが「承認」の投稿だけが公開されます。

詳しい計画(構成図・費用試算・スケジュール・リスク)は、フェーズ1レポートのArtifactを参照してください(チャットで共有済みのリンク)。

## ディレクトリ構成

```
docs/setup/        画面単位のセットアップ手順書(Anthropic API, GitHub Secrets, Googleスプレッドシート, WIF連携, Cloudflare Pages)
docs/sheets-design.md   Googleスプレッドシート10シートの設計仕様
sheets/             スプレッドシートを自動生成するGoogle Apps Script
agents/             8種類のAIエージェントのプロンプト定義(Markdown)
scripts/            Anthropic API呼び出し・Sheets連携・コスト管理・週次パイプラインのPythonコード
tests/              コスト管理ロジックの自動テスト
.github/workflows/  GitHub Actionsの定時実行ワークフロー(毎週自動実行)
site/               Cloudflare Pagesで公開する比較記事・LP(フェーズ5)
cost_log/           API利用額の記録(usage_log.json)
```

## セットアップの順番(完了済み)

1. `docs/setup/03_anthropic_api.md` — Anthropic APIキーの発行と月間上限の設定 ✅
2. `docs/setup/01_github_secrets.md` — 発行したキーをGitHubに安全に登録 ✅
3. `docs/setup/02_google_sheets.md` — 管理画面となるGoogleスプレッドシートの作成 ✅
4. `docs/setup/05_workload_identity_federation.md` — GitHub ActionsからGoogleスプレッドシートへの鍵なし連携 ✅
5. `docs/setup/04_cloudflare_pages.md` — 記事・LP公開の準備(フェーズ5で使用。今は読むだけでOK)

## 自動実行の仕組み(現状)

`.github/workflows/weekly_pipeline.yml` が毎週月曜7:00(JST)に自動起動し、
`scripts/weekly_pipeline.py` が企画→原稿を自動生成して、Googleスプレッドシートの
「企画候補」「投稿カレンダー」(ステータスは必ず「下書き」)「投稿原稿」に書き込みます。
**投稿の自動化はまだ行いません**(Instagram/YouTubeのアカウント・API連携が未整備のため)。
人間が週1回スプレッドシートを確認し、内容を見て「承認」に変更するまで一切公開されません。

## コスト管理の仕組み

- 通常の分類・要約・重複判定 → `claude-haiku-4-5`
- 企画・最終原稿・重要な校閲 → `claude-sonnet-5`
- すべての呼び出しの利用量とコストを `cost_log/usage_log.json` に記録
- 月間予算(既定3,000円)の **80%到達で新規コンテンツ生成を停止**、**100%到達で全API呼び出しを停止**
- 為替レートは `.env` の `USD_JPY_RATE`(既定160円/ドル、実勢より高めに設定し予算超過を防止)で調整

詳細は `scripts/budget_guard.py` を参照してください。

## テスト方法

APIキーなしで動作確認(コストゼロ):

```bash
pip install -r requirements.txt
python -m unittest discover tests
python scripts/run_test_generation.py --dry-run
```

画像・動画生成(`scripts/render_creative.py`)をローカルで試す場合は、あわせて以下も必要です
(GitHub Actionsの実行環境には標準でffmpegが入っており、Playwrightのブラウザは
ワークフロー内で自動インストールされるため、ローカルで試さない限り不要です)。

```bash
playwright install --with-deps chromium
# ffmpegが無い場合(Ubuntu/Debianの例):
sudo apt-get install -y ffmpeg
```

実際にAnthropic APIを呼んでテスト生成する場合(少額課金が発生します):

```bash
cp .env.example .env   # ANTHROPIC_API_KEY等を設定
python scripts/run_test_generation.py
```

## 開発の原則

- 有料サービスの追加、広告費・契約・購入・外部送信は人間の承認なしに行いません。
- SNS公式APIと利用規約を守り、規約違反となる自動化(自動フォロー等)は実装しません。
- アフィリエイト投稿には広告・PR表記を必ず付けます。
- APIキーはコード・スプレッドシート・ログに書かず、GitHub Secretsまたは`.env`(gitignore対象)で管理します。

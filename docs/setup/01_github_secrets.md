# 手順1: GitHub Secretsへのキー登録

Anthropic APIキーなどの秘密情報は、コードやスプレッドシートに書かず、GitHubの
「Secrets」という安全な保管場所に登録します。ここに登録した値は、GitHub Actions
(自動実行)からしか読み取れず、画面上にも表示されません。

## 前提

- `docs/setup/03_anthropic_api.md` で発行したAPIキー(`sk-ant-...`)を手元に用意しておく。
- このリポジトリ(`-ai-recruiting-media-agent`)の管理者権限があること。

## 手順

1. ブラウザでこのリポジトリのGitHubページを開く。
2. 上部タブの「**Settings**」をクリックする(リポジトリ全体の設定画面)。
3. 左メニューの「**Secrets and variables**」→「**Actions**」をクリックする。
4. 「**Repository secrets**」タブが選ばれていることを確認する。
5. 右上の「**New repository secret**」ボタンをクリックする。
6. 「Name」欄に `ANTHROPIC_API_KEY` と入力する(大文字・アンダースコアも正確に)。
7. 「Secret」欄に、コピーしておいたAPIキー(`sk-ant-...`)を貼り付ける。
8. 「**Add secret**」ボタンをクリックして保存する。
9. 一覧に `ANTHROPIC_API_KEY` が表示されれば完了。

## 今後、同じ画面で追加していく予定のSecret一覧(フェーズが進むごとに案内します)

| Secret名 | いつ必要か |
|---|---|
| `ANTHROPIC_API_KEY` | 今すぐ(フェーズ2) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | フェーズ2後半(スプレッドシート連携時) |
| `IG_ACCESS_TOKEN` / `IG_BUSINESS_ACCOUNT_ID` | フェーズ3(Instagram投稿連携時) |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_REFRESH_TOKEN` | フェーズ3(YouTube連携時) |
| `CLOUDFLARE_API_TOKEN` | フェーズ5(必要な場合のみ。通常はCloudflare側のGit連携で自動化するため不要) |

## 確認方法

- 「Settings」→「Secrets and variables」→「Actions」の一覧に、登録したSecret名だけが
  表示され、値そのものは表示されないことを確認してください(これが正しい状態です)。

# 手順5(実施済み記録): GitHub Actions ↔ Google Cloud の鍵なし連携

このリポジトリの組織(lifterworks.com)は、Google Cloudの組織ポリシーで
「サービスアカウントの静的JSONキー作成」自体をブロックしています
(`iam.managed.disableServiceAccountKeyCreation`)。そのため、JSONキーファイルを
一切使わない **Workload Identity Federation(WIF)** という方式で、GitHub Actionsが
このリポジトリからの実行時だけGoogle スプレッドシートを読み書きできるようにしました。

この設定は完了済みです。このドキュメントは「何を、なぜ設定したか」の記録です。
作り直す必要が生じた場合は、以下のコマンドをGoogle Cloud ConsoleのCloud Shellで
再実行してください。

## 設定した内容

| 項目 | 値 |
|---|---|
| Google Cloudプロジェクト | `recruiting-media-agent` |
| プロジェクト番号 | `532132424145` |
| Workload Identityプール | `github-actions-pool` |
| プロバイダ | `github-actions-provider` |
| 信頼するGitHubリポジトリ | `sato0929-com/-ai-recruiting-media-agent`(このリポジトリのみ。他のリポジトリやユーザーからはなりすませない) |
| サービスアカウント | `sheets-bot@recruiting-media-agent.iam.gserviceaccount.com` |
| このサービスアカウントの権限 | 対象のGoogleスプレッドシートの「編集者」(スプレッドシート単位で共有。Google Cloud全体のロールは付与していない) |

## 実施したコマンド(Cloud Shellで実行)

```bash
# 1. 必要なAPIを有効化
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com

# 2. Workload Identityプールを作成
gcloud iam workload-identity-pools create "github-actions-pool" \
  --location="global" \
  --display-name="GitHub Actions Pool"

# 3. GitHub Actionsを信頼するOIDCプロバイダを作成
#    (このリポジトリからのトークンだけを受け付けるよう attribute-condition で制限)
gcloud iam workload-identity-pools providers create-oidc "github-actions-provider" \
  --location="global" \
  --workload-identity-pool="github-actions-pool" \
  --display-name="GitHub Actions Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='sato0929-com/-ai-recruiting-media-agent'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# 4. サービスアカウント sheets-bot@recruiting-media-agent.iam.gserviceaccount.com に対し、
#    このリポジトリからだけ「なりすまし」を許可する
gcloud iam service-accounts add-iam-policy-binding \
  "sheets-bot@recruiting-media-agent.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/532132424145/locations/global/workloadIdentityPools/github-actions-pool/attribute.repository/sato0929-com/-ai-recruiting-media-agent"
```

さらに、対象のGoogleスプレッドシートを `sheets-bot@recruiting-media-agent.iam.gserviceaccount.com`
に「編集者」として共有しています(スプレッドシートの「共有」ボタンから実施)。

## GitHub Actions側の使い方

`.github/workflows/weekly_pipeline.yml` の中で、以下のように鍵ファイルなしで認証しています。

```yaml
permissions:
  id-token: write   # これがないとWIF認証できない

steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: projects/532132424145/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions-provider
      service_account: sheets-bot@recruiting-media-agent.iam.gserviceaccount.com
```

このステップの後は、Pythonの `google.auth.default()` が自動的にこの認証情報を使うため、
`scripts/sheets_client.py` はキーファイルのパスなどを一切知らなくてよい設計になっています。

## ローカルで試したい場合

自分のパソコンから `scripts/weekly_pipeline.py` を直接試したい場合は、事前に以下を実行してください
(これも鍵ファイルを作らない方法です)。

```bash
gcloud auth application-default login --project recruiting-media-agent
```

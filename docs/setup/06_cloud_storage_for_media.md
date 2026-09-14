# 手順6(実施済み記録): 投稿画像・動画の公開置き場(Cloud Storage)

Instagram Graph API(コンテンツ公開)は、画像・動画ファイルを直接送る方式ではなく、
「この公開URLの画像/動画を使ってください」という指定方式です。そのため、
生成したカルーセル画像・Shorts動画を投稿の直前に一時的に置く「公開URLの場所」が必要でした。

新しいアカウントは作らず、既存のGoogle Cloudプロジェクト(`recruiting-media-agent`)に
Cloud Storageのバケット(保管庫)を1つ追加する形で対応しています。

## 設定した内容

| 項目 | 値 |
|---|---|
| バケット名 | `recruiting-media-agent-assets` |
| リージョン | `asia-northeast1`(東京) |
| 公開設定 | バケット全体を`allUsers`に対して読み取り専用で公開(投稿予定の画像・動画のみを保存するため、公開されても問題ない) |
| 書き込み権限 | `sheets-bot@recruiting-media-agent.iam.gserviceaccount.com`(Google Sheets連携と同じサービスアカウントを流用) |

## 実施したコマンド(Cloud Shell)

```bash
# 1. Cloud Storage APIを有効化
gcloud services enable storage.googleapis.com

# 2. バケットを作成
gcloud storage buckets create gs://recruiting-media-agent-assets \
  --location=asia-northeast1 \
  --uniform-bucket-level-access

# 3. 誰でも読み取れるようにする(投稿する画像・動画なので公開して問題ない)
gcloud storage buckets add-iam-policy-binding gs://recruiting-media-agent-assets \
  --member=allUsers \
  --role=roles/storage.objectViewer

# 4. GitHub Actions(sheets-bot)からアップロードできるようにする
gcloud storage buckets add-iam-policy-binding gs://recruiting-media-agent-assets \
  --member=serviceAccount:sheets-bot@recruiting-media-agent.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

## 仕組み(2026-09-14更新: 署名付きURL方式に変更)

上記の「バケット全体をallUsersに公開」する設定は、実際にInstagram側から画像を
取得しようとしたところ403エラー(`Anonymous caller does not have
storage.objects.get access`)になり失敗しました。原因は、御社のGoogle Workspace
組織にかかっているセキュリティポリシー(Public Access Prevention、匿名公開を
組織全体で禁止する設定)により、上記のIAM設定(allUsersへのobjectViewer付与)が
実際には無効化されていたためです。

そのため、バケットを公開する方式はやめ、投稿の瞬間だけ有効な「署名付きURL
(V4 signed URL、有効期限15分)」を発行する方式に変更しました。この方式なら、
組織のPublic Access Preventionポリシーとは無関係に動作し、かつ生成した画像が
ネット上に恒久的に公開され続けることもないため、セキュリティ的にもより安全です。

### 追加で実施が必要なコマンド(Cloud Shell)

署名付きURLの発行には、サービスアカウントが自分自身を一時的に借用(インパーソネート)
できる権限が必要です(WIF経由の認証には秘密鍵がなく、直接署名できないため)。

```bash
gcloud iam service-accounts add-iam-policy-binding \
  sheets-bot@recruiting-media-agent.iam.gserviceaccount.com \
  --member="serviceAccount:sheets-bot@recruiting-media-agent.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### コードの仕組み

`scripts/storage_client.py` が、`scripts/publishing.py` から呼ばれ、
生成された画像・動画を `gs://recruiting-media-agent-assets/instagram/...` のような
パスにアップロードし、15分間だけ有効な署名付きURLを返します。このURLを
Instagram Graph APIの `image_url` パラメータに渡します。

認証はこれまでと同様、鍵ファイルを使わずWorkload Identity Federation経由のADCを使います
(`docs/setup/05_workload_identity_federation.md` 参照)。署名付きURLの発行部分だけ、
上記の自己インパーソネーション権限を使ってIAM Credentials API経由で署名しています。

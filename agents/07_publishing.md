# 投稿エージェント (Publishing)

## 役割
「承認」ステータスの投稿だけを、Instagram Graph API / YouTube Data APIで予約投稿し、結果を記録する。

## 使用モデルについて
このエージェントの中心処理は決定的なロジック(状態チェック・API呼び出し・再試行)であり、
基本的にLLMを使わない。投稿本文の軽微なフォーマット調整が必要な場合のみ `claude-haiku-4-5` を使う。

## 絶対に守ること(共通ポリシーに加えて)
- 「投稿カレンダー」シートのステータスが **「承認」** の行だけを処理対象にする。
  「承認待ち」「AI校閲済み」「下書き」は絶対に投稿しない。
- 投稿前に、対象行が本番用アカウント向けか、テスト用アカウント向けかを確認する
  (初期運用ではテスト用/非公開アカウントのみを対象にする)。

## 処理フロー(疑似コード)

```
for row in 投稿カレンダー.filter(status == "承認"):
    if row.scheduled_at > now: continue
    try:
        result = call_platform_api(row)  # Instagram Graph API または YouTube Data API
        投稿実績.append({post_id, url, posted_at: now, status: "成功"})
        row.status = "投稿済み"
        consecutive_failures = 0
    except PlatformAPIError as e:
        エラーログ.append({row_id, error: str(e), retried: retry_count})
        if retry_count < MAX_RETRY:
            retry_count += 1
            schedule_retry(row)
        else:
            row.status = "エラー"
            consecutive_failures += 1

    if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
        stop_all_publishing()
        notify_human("投稿が連続で失敗したため処理を停止しました")
```

## 記録する項目(「投稿実績」シート)
- 投稿ID、投稿URL、投稿日時、プラットフォーム、成功/失敗、リトライ回数

## パラメータ(初期値。docs/setup で調整可能)
- `MAX_RETRY`: 3回
- `CONSECUTIVE_FAILURE_LIMIT`: 3回連続失敗で全体停止

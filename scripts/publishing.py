"""投稿エージェント: 「投稿カレンダー」でステータスが「承認」の行だけを実際に投稿する。

絶対に守ること(agents/07_publishing.md 参照):
- ステータスが「承認」の行だけを処理する。「下書き」「AI校閲済み」「承認待ち」は絶対に投稿しない。
- 投稿後は「投稿実績」に記録し、「投稿カレンダー」のステータスを「投稿済み」に更新する。
- 失敗時は再試行(最大MAX_RETRY回)し、連続してCONSECUTIVE_FAILURE_LIMIT回失敗したら
  全体の処理を止める。
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import config  # noqa: E402
import render_creative  # noqa: E402
import sheets_client  # noqa: E402
import storage_client  # noqa: E402

MAX_RETRY = 3
CONSECUTIVE_FAILURE_LIMIT = 3
# 「IG」で始まるトークン(Instagramへの直接ログインで発行される新方式)は
# graph.facebook.comでは解析できず「Cannot parse access token」になる。
# その場合はgraph.instagram.comを使う必要がある(診断ログで先頭2文字を確認した結果、
# このプロジェクトのトークンはこちらの方式だと判明した)。
GRAPH_API_BASE = "https://graph.instagram.com/v21.0"

# 投稿カレンダーのステータス列(A列を1として6列目=F列)
CALENDAR_STATUS_COLUMN = "F"

JST = timezone(timedelta(hours=9))


def _today_jst() -> date:
    return datetime.now(JST).date()


def _is_due(scheduled_value: str) -> bool:
    """「投稿予定日時」列を見て、今日(JST)以降に投稿してよいかを判定する。

    列が空の場合(手動テスト投稿など)は、これまで通り承認され次第すぐ投稿する。
    日付の解析に失敗した場合も同様に、投稿を止めないため「投稿してよい」とみなす。"""
    value = (scheduled_value or "").strip()
    if not value:
        return True
    try:
        scheduled_date = datetime.fromisoformat(value).date()
    except ValueError:
        return True
    return scheduled_date <= _today_jst()


def _chunk_script(text: str, chars_per_chunk: int = 25, chars_per_sec: float = 6.0) -> list[dict]:
    """YouTube Shorts用ナレーション原稿を字幕チャンクに分割する簡易ロジック(API呼び出しなし)。"""
    sentences = re.split(r"(?<=[。！？])", text)
    chunks = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        for i in range(0, len(sentence), chars_per_chunk):
            piece = sentence[i : i + chars_per_chunk]
            duration = max(2, round(len(piece) / chars_per_sec))
            chunks.append({"text": piece, "duration_sec": duration})
    return chunks or [{"text": text[:chars_per_chunk], "duration_sec": 3}]


def _graph_call(method: str, url: str, **kwargs):
    """Graph APIを呼び出し、失敗時はMetaが返す詳細なエラーメッセージ(error.message等)を
    例外メッセージに含める。requests.raise_for_status() だけだと 'Bad Request' としか
    分からず、エラーログを見ても原因が特定できないため。"""
    resp = requests.request(method, url, timeout=60, **kwargs)
    if not resp.ok:
        try:
            detail = resp.json().get("error", {})
            message = detail.get("error_user_msg") or detail.get("message") or resp.text
        except ValueError:
            message = resp.text
        raise RuntimeError(f"Instagram Graph APIエラー({resp.status_code}) {url}: {message}")
    return resp.json()


def _wait_for_media_ready(media_id: str, token: str, timeout_sec: int = 90, interval_sec: int = 3) -> None:
    """Instagram側での画像/カルーセルの処理には数秒〜数十秒かかることがあり、完了前に
    media_publishを呼ぶと「The media is not ready for publishing」エラーになる。
    status_codeがFINISHEDになるまで待つ。"""
    deadline = time.monotonic() + timeout_sec
    while True:
        result = _graph_call(
            "get", f"{GRAPH_API_BASE}/{media_id}", params={"fields": "status_code", "access_token": token}
        )
        status = result.get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram側でのメディア処理に失敗しました(media_id={media_id})")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Instagram側でのメディア処理が{timeout_sec}秒たっても完了しませんでした(media_id={media_id})")
        time.sleep(interval_sec)


def _post_instagram_carousel(image_urls: list[str], caption: str) -> str:
    token = config.IG_ACCESS_TOKEN
    ig_user_id = config.IG_BUSINESS_ACCOUNT_ID

    if len(image_urls) == 1:
        result = _graph_call(
            "post",
            f"{GRAPH_API_BASE}/{ig_user_id}/media",
            data={"image_url": image_urls[0], "caption": caption, "access_token": token},
        )
        creation_id = result["id"]
    else:
        child_ids = []
        for url in image_urls:
            result = _graph_call(
                "post",
                f"{GRAPH_API_BASE}/{ig_user_id}/media",
                data={"image_url": url, "is_carousel_item": "true", "access_token": token},
            )
            child_ids.append(result["id"])
        # 各子画像の処理が終わっていないと、親のカルーセルコンテナ作成やpublishで
        # エラーになることがあるため、子1枚ずつ処理完了を待ってから親を作る。
        for child_id in child_ids:
            _wait_for_media_ready(child_id, token)
        result = _graph_call(
            "post",
            f"{GRAPH_API_BASE}/{ig_user_id}/media",
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
                "caption": caption,
                "access_token": token,
            },
        )
        creation_id = result["id"]

    # コンテナ(単一画像 or カルーセル全体)の処理が終わるまで待ってからpublishする。
    # 直後にpublishすると「The media is not ready for publishing」になることがある。
    _wait_for_media_ready(creation_id, token)

    result = _graph_call(
        "post",
        f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
    )
    media_id = result["id"]

    result = _graph_call(
        "get", f"{GRAPH_API_BASE}/{media_id}", params={"fields": "permalink", "access_token": token}
    )
    return result.get("permalink", f"https://www.instagram.com/p/{media_id}/")


def _post_youtube_short(video_path: Path, title: str, description: str) -> str:
    credentials = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    youtube = build("youtube", "v3", credentials=credentials)
    body = {
        "snippet": {"title": title[:100], "description": description, "categoryId": "22"},
        # 最初はunlisted(限定公開)で運用する。問題なければ将来publicに切り替える。
        "status": {"privacyStatus": "unlisted"},
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    return f"https://youtube.com/shorts/{response['id']}"


def _publish_instagram(draft_row: list) -> str:
    caption = draft_row[2] if len(draft_row) > 2 else ""
    slides_json = draft_row[3] if len(draft_row) > 3 else "[]"
    slides = json.loads(slides_json) if slides_json else []
    if not slides:
        raise ValueError("カルーセルスライドがありません")

    with tempfile.TemporaryDirectory() as tmp:
        image_paths = render_creative.render_carousel(slides, Path(tmp))
        image_urls = [
            storage_client.upload_public_file(p, f"instagram/{uuid.uuid4().hex}_{p.name}")
            for p in image_paths
        ]
        return _post_instagram_carousel(image_urls, caption)


def _publish_youtube(draft_row: list) -> str:
    caption = draft_row[2] if len(draft_row) > 2 else ""
    script = draft_row[4] if len(draft_row) > 4 else ""
    if not script:
        raise ValueError("YouTube台本がありません")
    chunks = _chunk_script(script)

    with tempfile.TemporaryDirectory() as tmp:
        video_path = render_creative.render_shorts_video(chunks, Path(tmp) / "short.mp4")
        title = (caption or script)[:90]
        return _post_youtube_short(video_path, title, caption)


def _record_error(calendar_id: str, message: str, retried: int = 0) -> None:
    now = datetime.now(timezone.utc).isoformat()
    sheets_client.append_rows(
        "エラーログ", [[now, "publishing", message, calendar_id, retried, "未対応", "", ""]]
    )


def _log_token_shape(name: str, value: str) -> None:
    """トークンの中身は一切出力せず、形がおかしくないかだけをログに出す。
    「Cannot parse access token」が空白混入以外の原因(JSON丸ごとや
    引用符の混入、トークン形式そのものの誤りなど)によるものかを、
    値そのものを見せずに切り分けるための診断ログ。"""
    if not value:
        print(f"[診断] {name}: 未設定(空文字列)")
        return
    has_whitespace = value != value.strip() or any(c.isspace() for c in value)
    suspicious_chars = {
        "引用符(\"や')": any(c in value for c in "\"'"),
        "波括弧({や})": any(c in value for c in "{}"),
        "コロン(:)": ":" in value,
        "カンマ(,)": "," in value,
        "スラッシュ(/)": "/" in value,
    }
    found_suspicious = [label for label, present in suspicious_chars.items() if present]
    allowed_charset_only = bool(re.fullmatch(r"[A-Za-z0-9_\-.]+", value))
    print(
        f"[診断] {name}: 文字数={len(value)} 空白混入={has_whitespace} "
        f"英数字と_-.のみで構成={allowed_charset_only} "
        f"不審な文字={found_suspicious or 'なし'} "
        f"先頭2文字={value[:2]!r} 末尾2文字={value[-2:]!r}"
    )


def run() -> None:
    _log_token_shape("IG_ACCESS_TOKEN", config.IG_ACCESS_TOKEN)
    _log_token_shape("IG_BUSINESS_ACCOUNT_ID", config.IG_BUSINESS_ACCOUNT_ID)

    calendar_rows = sheets_client.read_rows("投稿カレンダー")
    draft_rows = sheets_client.read_rows("投稿原稿")
    drafts_by_calendar_id = {r[1]: r for r in draft_rows if len(r) > 1}

    consecutive_failures = 0
    published_count = 0

    for i, row in enumerate(calendar_rows):
        sheet_row_number = i + 2  # ヘッダー行(1行目)を除く
        if len(row) < 6 or row[5] != "承認":
            continue
        scheduled_value = row[2] if len(row) > 2 else ""
        if not _is_due(scheduled_value):
            continue  # 予定日がまだ先なので、この行は今回は投稿しない

        calendar_id = row[0]
        platform = row[3] if len(row) > 3 else ""
        draft = drafts_by_calendar_id.get(calendar_id)
        if not draft:
            _record_error(calendar_id, "対応する投稿原稿が見つかりません")
            continue

        succeeded = False
        last_error = ""
        for attempt in range(1, MAX_RETRY + 1):
            try:
                if platform == "Instagram":
                    url = _publish_instagram(draft)
                elif platform == "YouTube Shorts":
                    url = _publish_youtube(draft)
                else:
                    raise ValueError(f"未対応のプラットフォームです: {platform}")

                now = datetime.now(timezone.utc).isoformat()
                sheets_client.append_rows(
                    "投稿実績",
                    [[str(uuid.uuid4())[:8], calendar_id, platform, url, now, "", "", "", "", "", now]],
                )
                sheets_client.update_cell("投稿カレンダー", sheet_row_number, CALENDAR_STATUS_COLUMN, "投稿済み")
                succeeded = True
                published_count += 1
                break
            except Exception as e:  # noqa: BLE001
                last_error = str(e)

        if succeeded:
            consecutive_failures = 0
        else:
            sheets_client.update_cell("投稿カレンダー", sheet_row_number, CALENDAR_STATUS_COLUMN, "エラー")
            _record_error(calendar_id, last_error, retried=MAX_RETRY)
            consecutive_failures += 1

        if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
            print(f"{CONSECUTIVE_FAILURE_LIMIT}件連続で投稿に失敗したため、処理を停止します。")
            break

    print(f"投稿処理が完了しました。成功: {published_count}件")


if __name__ == "__main__":
    run()

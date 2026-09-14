"""生成した画像・動画をCloud Storageにアップロードし、公開URLを返す。

Instagram Graph API(コンテンツ公開)は画像・動画をファイルとして直接受け取れず、
「公開されたURL」を指定する方式のため、投稿の直前に一時的な置き場としてここにアップロードする。
認証はサービスアカウントの鍵ファイルを使わず、Google Sheetsと同じADC(Workload Identity
Federation)を使う。
"""
from __future__ import annotations

from pathlib import Path

from google.cloud import storage

from config import GCS_BUCKET_NAME

_client = None


def _get_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def upload_public_file(local_path: Path, remote_path: str) -> str:
    """ファイルをアップロードし、公開URLを返す。バケットは全体を公開読み取りに設定済み。"""
    client = _get_client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(remote_path)
    blob.upload_from_filename(str(local_path))
    return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{remote_path}"

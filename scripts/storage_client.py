"""生成した画像・動画をCloud Storageにアップロードし、期限付きの署名付きURLを返す。

Instagram Graph API(コンテンツ公開)は画像・動画をファイルとして直接受け取れず、
「公開されたURL」を指定する方式のため、投稿の直前に一時的な置き場としてここに
アップロードする。

当初はバケット全体をallUsersに公開する方式にしていたが、Google Workspace組織の
セキュリティポリシー(Public Access Prevention)により匿名アクセスが実際には拒否
されており、Instagram側が画像を取得できなかった(403 AccessDenied)。そのため、
バケットは公開せず、投稿の瞬間だけ有効な署名付きURL(V4 signed URL)を発行する
方式に変更した。

認証はサービスアカウントの鍵ファイルを使わず、Workload Identity Federation経由の
ADCを使う。ただし署名付きURLの発行(sign_bytes)には秘密鍵を持つ認証情報が必要で、
WIF経由のADCはそれを持たない。そのため、サービスアカウントが自分自身に対して
`roles/iam.serviceAccountTokenCreator`を持つようにし(docs/setup/06参照)、
IAM Credentials API経由での署名(自己インパーソネーション)を使う。
"""
from __future__ import annotations

import datetime
from pathlib import Path

import google.auth
from google.auth import impersonated_credentials
from google.cloud import storage

from config import GCS_BUCKET_NAME, GCS_SIGNING_SERVICE_ACCOUNT

_client = None
_signing_credentials = None


def _get_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def _get_signing_credentials():
    global _signing_credentials
    if _signing_credentials is None:
        source_credentials, _ = google.auth.default()
        _signing_credentials = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=GCS_SIGNING_SERVICE_ACCOUNT,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
            lifetime=300,
        )
    return _signing_credentials


def upload_public_file(local_path: Path, remote_path: str) -> str:
    """ファイルをアップロードし、15分間だけ有効な署名付きURLを返す。"""
    client = _get_client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(remote_path)
    blob.upload_from_filename(str(local_path))
    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=15),
        method="GET",
        credentials=_get_signing_credentials(),
    )

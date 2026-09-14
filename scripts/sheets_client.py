"""Googleスプレッドシートの読み書き。

認証はサービスアカウントのJSON鍵を一切使わない。Application Default Credentials(ADC)を
使い、GitHub Actions上では google-github-actions/auth アクションがWorkload Identity
Federation経由でこのADCを用意する。ローカルで試す場合は事前に
`gcloud auth application-default login --project recruiting-media-agent` を実行しておく。
"""
from __future__ import annotations

import google.auth
from googleapiclient.discovery import build

from config import GOOGLE_SHEETS_SPREADSHEET_ID

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_service = None


def _get_service():
    global _service
    if _service is None:
        credentials, _ = google.auth.default(scopes=SCOPES)
        _service = build("sheets", "v4", credentials=credentials)
    return _service


def append_rows(sheet_name: str, rows: list[list]) -> None:
    """指定シートの末尾に行を追加する(既存データは変更しない)。"""
    service = _get_service()
    service.spreadsheets().values().append(
        spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def read_rows(sheet_name: str, cell_range: str = "A2:Z1000") -> list[list]:
    """指定シートの範囲を読み取る(既定はヘッダー行を除く2行目以降)。"""
    service = _get_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID, range=f"{sheet_name}!{cell_range}")
        .execute()
    )
    return result.get("values", [])


def update_cell(sheet_name: str, row_number: int, column_letter: str, value) -> None:
    """1つのセルを更新する(例: update_cell("投稿カレンダー", 2, "F", "投稿済み"))。"""
    service = _get_service()
    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
        range=f"{sheet_name}!{column_letter}{row_number}",
        valueInputOption="USER_ENTERED",
        body={"values": [[value]]},
    ).execute()

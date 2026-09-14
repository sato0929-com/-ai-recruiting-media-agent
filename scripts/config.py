"""環境変数と定数の読み込み。APIキーなど秘密情報はここに書き込まない。"""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

# --- モデル ---
# 通常の分類・要約・重複判定はHaiku、企画・最終原稿・重要な校閲のみSonnetを使う。
MODEL_HAIKU = "claude-haiku-4-5"
MODEL_SONNET = "claude-sonnet-5"

# 1Mトークンあたりの価格(米ドル)。Anthropic公式料金表が変わったらここを更新する。
# 参照: docs/setup/03_anthropic_api.md
PRICING_USD_PER_MTOK = {
    MODEL_HAIKU: {"input": 1.00, "output": 5.00},
    MODEL_SONNET: {"input": 2.00, "output": 10.00},
}

# --- コスト管理 ---
# `os.environ.get(key, default)` だと、GitHub Actionsの未設定vars(空文字列 "")が
# 渡された場合にdefaultへ落ちずエラーになるため、空文字列も「未設定」として扱う。
MONTHLY_BUDGET_JPY = float(os.environ.get("MONTHLY_BUDGET_JPY") or "3000")
# 実勢レートより高めにしておくと、円換算コストを保守的(高め)に見積もれる。
USD_JPY_RATE = float(os.environ.get("USD_JPY_RATE") or "160")
SOFT_LIMIT_RATIO = 0.8  # この割合に達したら新規コンテンツ生成を停止

# --- 保存先 ---
COST_LOG_PATH = REPO_ROOT / "cost_log" / "usage_log.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --- Googleスプレッドシート ---
# 認証はサービスアカウントの鍵ファイルを使わず、Workload Identity Federation経由の
# Application Default Credentials(ADC)を使う。ローカル実行時は
# `gcloud auth application-default login` を、GitHub Actions上では
# google-github-actions/auth アクションを使う(docs/setup/05_workload_identity_federation.md 参照)。
GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")

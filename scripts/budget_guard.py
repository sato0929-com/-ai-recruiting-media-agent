"""Anthropic API利用額の記録と、月間予算の強制停止ロジック。

要件:
- 1日/1週間/1か月ごとの利用額を記録する
- 月間予算の80%に達したら新規コンテンツ生成(企画・原稿・素材)を停止する
- 月間予算の100%(超過)に達したら、すべてのAPI呼び出しを停止する(自動課金を続けない)
"""
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from config import (
    COST_LOG_PATH,
    MONTHLY_BUDGET_JPY,
    PRICING_USD_PER_MTOK,
    SOFT_LIMIT_RATIO,
    USD_JPY_RATE,
    WEB_SEARCH_COST_USD_PER_SEARCH,
)

CallKind = Literal["generation", "utility"]


class SoftBudgetExceeded(Exception):
    """月間予算の80%に達し、新規コンテンツ生成を停止した。"""


class HardBudgetExceeded(Exception):
    """月間予算の100%に達し、すべてのAPI呼び出しを停止した。"""


@dataclass
class UsageEntry:
    timestamp: str  # ISO8601 UTC
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    web_search_count: int
    cost_usd: float  # トークン課金+Web検索課金の合計
    cost_jpy: float


def calc_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICING_USD_PER_MTOK[model]
    return (input_tokens / 1_000_000) * price["input"] + (output_tokens / 1_000_000) * price["output"]


def calc_web_search_cost_usd(web_search_count: int) -> float:
    return web_search_count * WEB_SEARCH_COST_USD_PER_SEARCH


def _load_entries(log_path: Path = COST_LOG_PATH) -> list[dict]:
    if not log_path.exists():
        return []
    with open(log_path, encoding="utf-8") as f:
        return json.load(f)


def _save_entries(entries: list[dict], log_path: Path = COST_LOG_PATH) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def record_usage(
    agent: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    web_search_count: int = 0,
    log_path: Path = COST_LOG_PATH,
) -> UsageEntry:
    cost_usd = calc_cost_usd(model, input_tokens, output_tokens) + calc_web_search_cost_usd(web_search_count)
    entry = UsageEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        agent=agent,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        web_search_count=web_search_count,
        cost_usd=round(cost_usd, 6),
        cost_jpy=round(cost_usd * USD_JPY_RATE, 2),
    )
    entries = _load_entries(log_path)
    entries.append(asdict(entry))
    _save_entries(entries, log_path)
    return entry


def _period_start(period: Literal["day", "week", "month"], now: datetime) -> datetime:
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(period)


def total_cost_jpy(
    period: Literal["day", "week", "month"], log_path: Path = COST_LOG_PATH, now: datetime | None = None
) -> float:
    now = now or datetime.now(timezone.utc)
    start = _period_start(period, now)
    total = 0.0
    for e in _load_entries(log_path):
        ts = datetime.fromisoformat(e["timestamp"])
        if ts >= start:
            total += e["cost_jpy"]
    return round(total, 2)


def check_before_call(kind: CallKind, log_path: Path = COST_LOG_PATH) -> None:
    """API呼び出しの直前に呼ぶ。予算超過時は例外を送出し、呼び出し元は処理を止めること。"""
    month_total = total_cost_jpy("month", log_path)
    if month_total >= MONTHLY_BUDGET_JPY:
        raise HardBudgetExceeded(
            f"月間予算{MONTHLY_BUDGET_JPY}円に対し利用額{month_total}円。全てのAPI呼び出しを停止します。"
        )
    if kind == "generation" and month_total >= MONTHLY_BUDGET_JPY * SOFT_LIMIT_RATIO:
        raise SoftBudgetExceeded(
            f"月間予算{MONTHLY_BUDGET_JPY}円の{SOFT_LIMIT_RATIO:.0%}({month_total}円)に到達。"
            "新規コンテンツ生成を停止します(分析・エラー記録などのutility呼び出しは継続可)。"
        )


def summary() -> dict:
    return {
        "today_jpy": total_cost_jpy("day"),
        "this_week_jpy": total_cost_jpy("week"),
        "this_month_jpy": total_cost_jpy("month"),
        "monthly_budget_jpy": MONTHLY_BUDGET_JPY,
        "soft_limit_jpy": round(MONTHLY_BUDGET_JPY * SOFT_LIMIT_RATIO, 2),
    }


if __name__ == "__main__":
    print(json.dumps(summary(), ensure_ascii=False, indent=2))

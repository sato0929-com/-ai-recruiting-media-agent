"""週次自動パイプライン本体(GitHub Actionsから自動実行される想定)。

企画→原稿までを自動生成し、Googleスプレッドシートに書き込む。
投稿の自動化はまだ行わない(Instagram/YouTubeのアカウント・API連携が未整備のため)。
書き込まれる「投稿カレンダー」のステータスは必ず「下書き」で、人間が確認して
「承認」に変更するまで一切公開されない。

リサーチ結果は今のところ scripts/run_test_generation.py のサンプルデータを使う
(実際のWeb検索連携は今後のフェーズで追加予定)。
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import budget_guard  # noqa: E402
import claude_client  # noqa: E402
import sheets_client  # noqa: E402
from run_test_generation import SAMPLE_RESEARCH, load_agent_prompt  # noqa: E402


def _platform_for(format_label: str) -> str:
    if "YouTube" in format_label:
        return "YouTube Shorts"
    return "Instagram"


def run() -> None:
    planning_system = load_agent_prompt("03_planning.md")
    writing_system = load_agent_prompt("04_writing.md")

    plan_text = claude_client.call_sonnet(
        system=planning_system,
        user_prompt="以下のリサーチ結果から、投稿企画案を2件作成してください。\n\n"
        + json.dumps(SAMPLE_RESEARCH, ensure_ascii=False, indent=2),
        agent="planning",
        kind="generation",
        max_tokens=2000,
    )
    try:
        plans = json.loads(plan_text)
    except json.JSONDecodeError:
        print("企画エージェントの出力がJSONとして解析できませんでした。処理を中断します。")
        print(plan_text)
        return
    if not plans:
        print("企画案が0件でした。処理を終了します。")
        return

    top_plan = max(plans, key=lambda p: p.get("scores", {}).get("合計", 0))

    draft_text = claude_client.call_sonnet(
        system=writing_system,
        user_prompt="以下の企画案から、Instagramカルーセル投稿の原稿一式を作成してください。\n\n"
        + json.dumps(top_plan, ensure_ascii=False, indent=2),
        agent="writing",
        kind="generation",
        max_tokens=3000,
    )
    try:
        draft = json.loads(draft_text)
    except json.JSONDecodeError:
        print("原稿エージェントの出力がJSONとして解析できませんでした。処理を中断します。")
        print(draft_text)
        return

    now = datetime.now(timezone.utc).isoformat()
    plan_id, calendar_id, draft_id = (str(uuid.uuid4())[:8] for _ in range(3))
    scores = top_plan.get("scores", {})
    caption = draft.get("caption", "")

    sheets_client.append_rows(
        "企画候補",
        [[
            plan_id, now, top_plan.get("title"), top_plan.get("angle"), top_plan.get("format"),
            ", ".join(top_plan.get("source_refs", [])),
            scores.get("専門性"), scores.get("需要"), scores.get("収益性"),
            scores.get("独自性"), scores.get("リスク"), scores.get("合計"),
            top_plan.get("duplicate_check"), top_plan.get("requires_human_approval"),
            top_plan.get("approval_reason", ""), "採用",
        ]],
    )

    sheets_client.append_rows(
        "投稿カレンダー",
        [[
            calendar_id, plan_id, "", _platform_for(top_plan.get("format", "")), "test",
            "下書き", "writing", now, "自動生成(要レビュー)",
        ]],
    )

    sheets_client.append_rows(
        "投稿原稿",
        [[
            draft_id, calendar_id, caption,
            json.dumps(draft.get("instagram_carousel", []), ensure_ascii=False),
            draft.get("youtube_shorts_script", ""), draft.get("cta", ""),
            caption.strip().startswith("[PR]"), "", "", 1, now,
        ]],
    )

    print(f"企画候補ID={plan_id} / 投稿カレンダーID={calendar_id} / 投稿原稿ID={draft_id} を書き込みました。")
    print(json.dumps(budget_guard.summary(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        run()
    except (budget_guard.SoftBudgetExceeded, budget_guard.HardBudgetExceeded) as e:
        print(f"予算上限のため処理を停止しました: {e}")
        raise SystemExit(1)

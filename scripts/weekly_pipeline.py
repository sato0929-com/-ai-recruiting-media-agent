"""週次自動パイプライン本体(GitHub Actionsから自動実行される想定)。

リサーチ→企画→原稿までを自動生成し、Googleスプレッドシートに書き込む。
投稿の自動化はまだ行わない(Instagram/YouTubeのアカウント・API連携が未整備のため)。
書き込まれる「投稿カレンダー」のステータスは必ず「下書き」で、人間が確認して
「承認」に変更するまで一切公開されない。

リサーチはClaudeのサーバーサイドWeb検索ツールを使う(2026-09-14〜)。
検索が失敗した場合のみ、scripts/run_test_generation.py の固定サンプルデータに
フォールバックする(処理を止めないため。ログに警告を出す)。
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import budget_guard  # noqa: E402
import claude_client  # noqa: E402
import sheets_client  # noqa: E402
from run_test_generation import SAMPLE_RESEARCH, load_agent_prompt  # noqa: E402

# 週次パイプライン1回の実行で、プラットフォームごとに作成する投稿本数
# (Instagram 4本 + YouTube Shorts 4本 = 週8本体制。2026-09-14変更)。
PLATFORM_POSTS_PER_RUN = {
    "Instagram": 4,
    "YouTube Shorts": 4,
}

# リサーチのテーマキーワード候補。毎週ローテーションして偏りを避ける。
RESEARCH_KEYWORD_SETS = [
    ["中小企業 採用 求人媒体 費用", "求人票 書き方 応募が集まる"],
    ["人事 採用業務 AIツール 活用事例", "採用担当者 業務効率化"],
    ["転職 求人 応募が増えない 原因", "採用ミスマッチ 対策"],
    ["中途採用 面接 選考プロセス 改善", "内定辞退 防止"],
]


def _research_keywords_for_this_week() -> list[str]:
    week_number = datetime.now(timezone.utc).isocalendar().week
    return RESEARCH_KEYWORD_SETS[week_number % len(RESEARCH_KEYWORD_SETS)]


def _run_research() -> list[dict]:
    research_system = load_agent_prompt("02_research.md")
    keywords = _research_keywords_for_this_week()
    try:
        research_text = claude_client.call_haiku(
            system=research_system,
            user_prompt="以下のテーマキーワードについて、Web検索を使って公開情報を調べ、"
            "指定のJSON形式で整理してください。\n\nテーマキーワード:\n"
            + "\n".join(f"- {k}" for k in keywords),
            agent="research",
            kind="generation",
            # 検索結果のテキスト自体が出力トークンを消費するため、最終的なJSON回答を書く前に
            # トークン上限に達して打ち切られないよう、十分大きめの上限にしておく。
            max_tokens=8000,
            enable_web_search=True,
            max_searches=6,
        )
        if not research_text.strip():
            print("リサーチのレスポンスが空でした(トークン上限に達した可能性)。サンプルデータにフォールバックします。")
            return SAMPLE_RESEARCH
        research = claude_client.parse_json_response(research_text)
        if research:
            return research
        print("リサーチ結果が0件でした。サンプルデータにフォールバックします。")
    except (budget_guard.SoftBudgetExceeded, budget_guard.HardBudgetExceeded):
        raise
    except Exception as e:  # noqa: BLE001
        print(f"リサーチ中にエラーが発生したため、サンプルデータにフォールバックします: {e}")
    return SAMPLE_RESEARCH


# 各プラットフォーム4本を月・水・金・日に自動で振り分ける(投稿カレンダーの「投稿予定日時」に設定)。
# publishing.py はこの日付が来るまでその行を投稿しない。人間がシート上でこの日付を
# 直接書き換えれば、個別に前後させることもできる。
POST_WEEKDAYS = [0, 2, 4, 6]  # 月=0, 水=2, 金=4, 日=6(datetime.weekday()準拠)


def _scheduled_dates_for_this_week(count: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=POST_WEEKDAYS[i % len(POST_WEEKDAYS)])).isoformat() for i in range(count)]


def _plan_for_platform(planning_system: str, research: list[dict], platform: str, count: int) -> list[dict]:
    """指定したプラットフォーム向けの企画案を、要求本数+2件作らせてスコア上位count件を返す。
    企画エージェントの自由判断に任せると本数がプラットフォーム間で偏るため、
    ここで明示的にプラットフォームごとに呼び分けて本数を保証する。"""
    format_label = "Instagramカルーセル" if platform == "Instagram" else "YouTube Shorts"
    plan_text = claude_client.call_sonnet(
        system=planning_system,
        user_prompt=f"以下のリサーチ結果から、{format_label}向けの投稿企画案を{count + 2}件作成してください。"
        f"すべての企画案の「フォーマット」は必ず{format_label}にしてください。"
        "同じリサーチ結果からでも、切り口(angle)が重複しないようにしてください。\n\n"
        + json.dumps(research, ensure_ascii=False, indent=2),
        agent="planning",
        kind="generation",
        max_tokens=3000,
    )
    try:
        plans = claude_client.parse_json_response(plan_text)
    except json.JSONDecodeError:
        print(f"企画エージェントの出力がJSONとして解析できませんでした({platform}向け)。この回はスキップします。")
        print(plan_text)
        return []
    return sorted(plans, key=lambda p: p.get("scores", {}).get("合計", 0), reverse=True)[:count]


CTA_BASE_URL = "https://liftercorp.co/contact"


def _add_utm_tracking(caption: str, platform: str, calendar_id: str) -> str:
    """CTAリンクにUTMパラメータを付与し、どの投稿経由の問い合わせかを後から追跡できるようにする
    (2026-09-15〜。目的はアフィリエイト収益ではなく、LIFTER自社の問い合わせ獲得のため)。
    原稿エージェントはCTAをこのベースURLのまま出力する前提(agents/04_writing.md参照)。"""
    utm_source = "instagram" if platform == "Instagram" else "youtube"
    tracked_url = f"{CTA_BASE_URL}?utm_source={utm_source}&utm_medium=social&utm_content={calendar_id}"
    return caption.replace(CTA_BASE_URL, tracked_url)


def _write_one(
    planning_system: str, writing_system: str, top_plan: dict, scheduled_date: str, platform: str
) -> None:
    draft_text = claude_client.call_sonnet(
        system=writing_system,
        user_prompt="以下の企画案から、投稿原稿一式を作成してください。\n\n"
        + json.dumps(top_plan, ensure_ascii=False, indent=2),
        agent="writing",
        kind="generation",
        max_tokens=3000,
    )
    try:
        draft = claude_client.parse_json_response(draft_text)
    except json.JSONDecodeError:
        print(f"原稿エージェントの出力がJSONとして解析できませんでした(企画: {top_plan.get('title')})。この1件をスキップします。")
        print(draft_text)
        return

    now = datetime.now(timezone.utc).isoformat()
    plan_id, calendar_id, draft_id = (str(uuid.uuid4())[:8] for _ in range(3))
    scores = top_plan.get("scores", {})
    caption = _add_utm_tracking(draft.get("caption", ""), platform, calendar_id)

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
            calendar_id, plan_id, scheduled_date, platform, "test",
            "下書き", "writing", now, "自動生成(要レビュー)",
        ]],
    )

    sheets_client.append_rows(
        "投稿原稿",
        [[
            draft_id, calendar_id, caption,
            json.dumps(draft.get("instagram_carousel", []), ensure_ascii=False),
            draft.get("youtube_shorts_script", ""),
            _add_utm_tracking(draft.get("cta", ""), platform, calendar_id),
            caption.strip().startswith("[PR]"), "", "", 1, now,
        ]],
    )

    print(f"企画候補ID={plan_id} / 投稿カレンダーID={calendar_id} / 投稿原稿ID={draft_id} を書き込みました。")


def run() -> None:
    planning_system = load_agent_prompt("03_planning.md")
    writing_system = load_agent_prompt("04_writing.md")

    research = _run_research()

    for platform, count in PLATFORM_POSTS_PER_RUN.items():
        try:
            top_plans = _plan_for_platform(planning_system, research, platform, count)
        except (budget_guard.SoftBudgetExceeded, budget_guard.HardBudgetExceeded):
            raise
        except Exception as e:  # noqa: BLE001
            print(f"{platform}向けの企画案作成中にエラーが発生したため、この回はスキップします: {e}")
            continue

        if not top_plans:
            print(f"{platform}向けの企画案が0件でした。この回はスキップします。")
            continue

        scheduled_dates = _scheduled_dates_for_this_week(len(top_plans))
        for top_plan, scheduled_date in zip(top_plans, scheduled_dates):
            try:
                _write_one(planning_system, writing_system, top_plan, scheduled_date, platform)
            except (budget_guard.SoftBudgetExceeded, budget_guard.HardBudgetExceeded):
                raise
            except Exception as e:  # noqa: BLE001
                print(f"企画「{top_plan.get('title')}」の原稿作成中にエラーが発生したためスキップします: {e}")

    print(json.dumps(budget_guard.summary(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        run()
    except (budget_guard.SoftBudgetExceeded, budget_guard.HardBudgetExceeded) as e:
        print(f"予算上限のため処理を停止しました: {e}")
        raise SystemExit(1)

"""テストデータを使って、企画エージェント→原稿エージェントの一連の流れを試すスクリプト。

--dry-run を付けるとAnthropic APIを一切呼ばず、処理の流れとプロンプトの中身だけを確認できる
(課金ゼロ)。付けない場合は実際にHaiku/Sonnetを呼び出し、少額の課金が発生する。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# テスト用のダミー・リサーチ結果(実在の個人情報や未確認の断定情報は含まない)
SAMPLE_RESEARCH = [
    {
        "title": "Indeedのスポンサー求人、クリック単価の傾向に関する解説記事",
        "source_url": "https://example.com/indeed-cpc-guide",
        "fetched_at": "2026-09-10",
        "published_at": "2026-08-20",
        "summary": (
            "Indeedのスポンサー求人はクリック課金制で、応募が集まりやすい職種ほど"
            "クリック単価が上がる傾向がある、という一般的な仕組みの解説。"
        ),
    },
    {
        "title": "中小企業の採用担当者を対象にしたAIツール活用に関する調査",
        "source_url": "https://example.com/sme-ai-recruiting-survey",
        "fetched_at": "2026-09-11",
        "published_at": "2026-09-01",
        "summary": (
            "中小企業の採用担当者のうち、選考プロセスにAIツールを一部でも導入している"
            "割合が増加傾向にある、という調査結果の紹介。"
        ),
    },
]


def load_agent_prompt(filename: str) -> str:
    """共通ポリシー(_shared_policies.md。エージェントではなく全エージェント共通の前提)を
    先頭に結合し、各エージェント固有の指示を続ける。"""
    shared = (REPO_ROOT / "agents" / "_shared_policies.md").read_text(encoding="utf-8")
    specific = (REPO_ROOT / "agents" / filename).read_text(encoding="utf-8")
    return shared + "\n\n---\n\n" + specific


def run_dry(research: list[dict]) -> None:
    print("=== DRY RUN(API呼び出しなし) ===")
    print("\n--- 企画エージェントに渡すシステムプロンプト(先頭300文字) ---")
    print(load_agent_prompt("03_planning.md")[:300], "...\n")
    print("--- 入力するリサーチ結果 ---")
    print(json.dumps(research, ensure_ascii=False, indent=2))
    print(
        "\n実際に生成するには `python scripts/run_test_generation.py` "
        "(--dry-runなし)を実行してください。ANTHROPIC_API_KEYが必要です。"
    )


def run_live(research: list[dict]) -> None:
    import claude_client

    planning_system = load_agent_prompt("03_planning.md")
    writing_system = load_agent_prompt("04_writing.md")

    print("=== 企画エージェント実行中(Sonnet) ===")
    plan_output = claude_client.call_sonnet(
        system=planning_system,
        user_prompt="以下のリサーチ結果から、投稿企画案を2件作成してください。\n\n"
        + json.dumps(research, ensure_ascii=False, indent=2),
        agent="planning",
        kind="generation",
        max_tokens=2000,
    )
    print(plan_output)

    print("\n=== 原稿エージェント実行中(Sonnet) ===")
    draft_output = claude_client.call_sonnet(
        system=writing_system,
        user_prompt="以下の企画案のうち1件目を使って、Instagramカルーセル投稿の原稿(スライド構成・"
        "投稿文・CTA)を作成してください。\n\n" + plan_output,
        agent="writing",
        kind="generation",
        max_tokens=3000,
    )
    print(draft_output)

    import budget_guard

    print("\n=== コストサマリー ===")
    print(json.dumps(budget_guard.summary(), ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="APIを呼ばずに処理内容だけ確認する")
    args = parser.parse_args()

    if args.dry_run:
        run_dry(SAMPLE_RESEARCH)
    else:
        run_live(SAMPLE_RESEARCH)


if __name__ == "__main__":
    main()

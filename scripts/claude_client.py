"""Anthropic API呼び出しの共通ラッパー。

- 呼び出し前に budget_guard.check_before_call() で予算を確認する。
- Haiku/Sonnetの振り分け、コスト記録をここに一本化し、各エージェントのスクリプトは
  call_haiku() / call_sonnet() を呼ぶだけでよいようにする。
"""
from __future__ import annotations

import json
import re

import anthropic

import budget_guard
from config import ANTHROPIC_API_KEY, MODEL_HAIKU, MODEL_SONNET

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY or None)
    return _client


def _extract_text(response: anthropic.types.Message) -> str:
    """レスポンスの最後のテキストブロックを返す。

    Web検索ツールを使った場合、response.contentには検索クエリ・検索結果の
    ブロックがテキストブロックの間に混在する(例: 「検索します」という前置き
    テキスト → 検索ツール呼び出し → 検索結果 → 最終的な回答テキスト)。
    全テキストブロックを連結すると前置き文言が最終出力(JSON)に混ざって
    しまうため、最後のテキストブロックだけを使う。"""
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return text_blocks[-1] if text_blocks else ""


def _extract_web_search_count(response: anthropic.types.Message) -> int:
    server_tool_use = getattr(response.usage, "server_tool_use", None)
    return getattr(server_tool_use, "web_search_requests", 0) or 0


def parse_json_response(text: str):
    """モデルの出力からJSONを取り出す。```json ... ``` のようなMarkdownの
    コードフェンスで囲まれていても、素のJSONだけを渡しても解析できる。"""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    if match:
        stripped = match.group(1).strip()
    return json.loads(stripped)


def _web_search_tool(max_searches: int) -> list[dict]:
    return [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]


def call_haiku(
    system: str,
    user_prompt: str,
    agent: str,
    kind: budget_guard.CallKind = "generation",
    max_tokens: int = 2048,
    enable_web_search: bool = False,
    max_searches: int = 5,
) -> str:
    """分類・要約・重複判定など、日常的に大量に呼ぶ処理向け。extended thinkingは使わない。"""
    budget_guard.check_before_call(kind)
    client = _get_client()
    kwargs = {"tools": _web_search_tool(max_searches)} if enable_web_search else {}
    response = client.messages.create(
        model=MODEL_HAIKU,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        **kwargs,
    )
    budget_guard.record_usage(
        agent, MODEL_HAIKU, response.usage.input_tokens, response.usage.output_tokens,
        web_search_count=_extract_web_search_count(response),
    )
    return _extract_text(response)


def call_sonnet(
    system: str,
    user_prompt: str,
    agent: str,
    kind: budget_guard.CallKind = "generation",
    max_tokens: int = 8000,
    effort: str = "medium",
    enable_web_search: bool = False,
    max_searches: int = 5,
) -> str:
    """企画・最終原稿・重要な校閲など、品質が重要な処理向け。"""
    budget_guard.check_before_call(kind)
    client = _get_client()
    kwargs = {"tools": _web_search_tool(max_searches)} if enable_web_search else {}
    response = client.messages.create(
        model=MODEL_SONNET,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        output_config={"effort": effort},
        **kwargs,
    )
    budget_guard.record_usage(
        agent, MODEL_SONNET, response.usage.input_tokens, response.usage.output_tokens,
        web_search_count=_extract_web_search_count(response),
    )
    return _extract_text(response)

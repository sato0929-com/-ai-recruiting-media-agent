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
    return "".join(block.text for block in response.content if block.type == "text")


def parse_json_response(text: str):
    """モデルの出力からJSONを取り出す。```json ... ``` のようなMarkdownの
    コードフェンスで囲まれていても、素のJSONだけを渡しても解析できる。"""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    if match:
        stripped = match.group(1).strip()
    return json.loads(stripped)


def call_haiku(
    system: str,
    user_prompt: str,
    agent: str,
    kind: budget_guard.CallKind = "generation",
    max_tokens: int = 2048,
) -> str:
    """分類・要約・重複判定など、日常的に大量に呼ぶ処理向け。extended thinkingは使わない。"""
    budget_guard.check_before_call(kind)
    client = _get_client()
    response = client.messages.create(
        model=MODEL_HAIKU,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    budget_guard.record_usage(agent, MODEL_HAIKU, response.usage.input_tokens, response.usage.output_tokens)
    return _extract_text(response)


def call_sonnet(
    system: str,
    user_prompt: str,
    agent: str,
    kind: budget_guard.CallKind = "generation",
    max_tokens: int = 8000,
    effort: str = "medium",
) -> str:
    """企画・最終原稿・重要な校閲など、品質が重要な処理向け。"""
    budget_guard.check_before_call(kind)
    client = _get_client()
    response = client.messages.create(
        model=MODEL_SONNET,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        output_config={"effort": effort},
    )
    budget_guard.record_usage(agent, MODEL_SONNET, response.usage.input_tokens, response.usage.output_tokens)
    return _extract_text(response)

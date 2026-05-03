"""Provider factory + retry wrapper.

Wraps an `LLMProvider` with cross-provider retry logic. Distinguishes:
  - rate-limit errors (back off)
  - transient connection / timeout errors (back off)
  - max-tokens / context-window errors (double max_tokens, no backoff)
"""

from __future__ import annotations

import re
import sys
import time
from typing import Optional

from .base import ChatResponse, LLMProvider


def make_provider(name: str) -> LLMProvider:
    name = name.lower()
    if name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider()
    raise ValueError(f"Unknown provider: {name}")


_RATE_LIMIT_HINTS = ("rate", "429", "tpm", "tokens per min", "quota")
_TRUNCATED_HINTS = ("max_tokens", "max output", "max tokens", "max_output_tokens")
_TRANSIENT_HINTS = ("timeout", "timed out", "connection", "ECONNRESET", "503", "502", "500")
_RETRY_HINT_RE = re.compile(r"try again in ([\d.]+)\s*s", re.IGNORECASE)


def _classify(err: Exception) -> str:
    s = str(err).lower()
    if any(h in s for h in _RATE_LIMIT_HINTS):
        return "rate"
    if any(h.lower() in s for h in _TRUNCATED_HINTS):
        return "truncated"
    if any(h.lower() in s for h in _TRANSIENT_HINTS):
        return "transient"
    return "fatal"


def _hint_seconds(err: Exception) -> Optional[float]:
    m = _RETRY_HINT_RE.search(str(err))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def chat_with_retry(
    provider: LLMProvider,
    *,
    model: str,
    messages: list[dict],
    tools: list[dict],
    tool_choice="auto",
    temperature: float = 0.9,
    max_tokens: Optional[int] = None,
    max_retries: int = 7,
) -> ChatResponse:
    backoff = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
    current_max_tokens = max_tokens
    truncate_doublings = 0
    last: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            return provider.chat(
                model=model, messages=messages, tools=tools,
                tool_choice=tool_choice, temperature=temperature,
                max_tokens=current_max_tokens,
            )
        except Exception as e:  # noqa: BLE001
            last = e
            kind = _classify(e)
            if kind == "fatal":
                raise
            if kind == "truncated" and current_max_tokens and truncate_doublings < 3:
                current_max_tokens *= 2
                truncate_doublings += 1
                print(f"[retry {attempt}] truncated; doubling max_tokens -> {current_max_tokens}",
                      file=sys.stderr)
                continue
            if attempt >= max_retries:
                break
            wait = backoff[min(attempt, len(backoff) - 1)]
            if kind == "rate":
                hint = _hint_seconds(e) or 0
                wait = max(wait, hint)
            print(f"[retry {attempt}] {kind}; sleeping {wait:.1f}s: {type(e).__name__}",
                  file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Provider call failed after retries: {last!r}")

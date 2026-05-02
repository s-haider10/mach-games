"""OpenAI client + retry wrapper.

Handles three classes of transient failure:
  - RateLimitError: backs off, honoring OpenAI's "try again in X.Ys" hint when present.
  - APIConnectionError / APITimeoutError: simple exponential backoff.
  - BadRequestError "max_tokens reached": doubles max_tokens and retries (tool-call
    JSON bodies can run long; a tight cap will truncate mid-arguments and get rejected).
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Optional

from openai import OpenAI
from openai import APIConnectionError, APITimeoutError, BadRequestError, RateLimitError


def make_client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set; export it before running pilot.")
    return OpenAI(api_key=key)


_RETRY_HINT_RE = re.compile(r"try again in ([\d.]+)s")
_MAX_TOKENS_RE = re.compile(r"max_tokens or model output limit was reached", re.IGNORECASE)


def _parse_retry_hint_seconds(msg: str) -> Optional[float]:
    m = _RETRY_HINT_RE.search(msg)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def chat_with_retry(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict],
    tools: list[dict],
    tool_choice: Any,
    temperature: float,
    max_tokens: Optional[int] = None,
) -> Any:
    """Up to 7 retries with exponential backoff and per-error tuning."""
    backoff = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
    last_err: Optional[Exception] = None
    current_max_tokens = max_tokens
    max_tokens_doublings = 0

    for attempt in range(len(backoff) + 1):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
        }
        if current_max_tokens is not None:
            kwargs["max_tokens"] = current_max_tokens

        try:
            return client.chat.completions.create(**kwargs)

        except RateLimitError as e:
            last_err = e
            if attempt >= len(backoff):
                break
            hint = _parse_retry_hint_seconds(str(e)) or 0.0
            wait = max(hint, backoff[attempt])
            print(
                f"[retry {attempt}] rate limit; sleeping {wait:.1f}s: {e!r}",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        except BadRequestError as e:
            # Specifically: max_tokens cap was reached. Double and retry, up to 3 times
            # (200 → 400 → 800 → 1600). Anything else 400-class is a real bug; re-raise.
            if not _MAX_TOKENS_RE.search(str(e)) or current_max_tokens is None:
                raise
            if max_tokens_doublings >= 3:
                raise
            new_cap = current_max_tokens * 2
            print(
                f"[retry {attempt}] max_tokens={current_max_tokens} truncated reply; "
                f"raising to {new_cap} and retrying.",
                file=sys.stderr,
            )
            current_max_tokens = new_cap
            max_tokens_doublings += 1
            # No backoff for this case — it's not a load issue.
            continue

        except (APIConnectionError, APITimeoutError) as e:
            last_err = e
            if attempt >= len(backoff):
                break
            wait = backoff[attempt]
            print(
                f"[retry {attempt}] transient {type(e).__name__}; sleeping {wait:.1f}s: {e!r}",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

    raise RuntimeError(f"OpenAI call failed after retries: {last_err!r}")

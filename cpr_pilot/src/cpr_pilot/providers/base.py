"""Provider abstraction. All LLM calls go through `LLMProvider.chat`.

The provider returns a uniform `ChatResponse` regardless of which API was hit,
so the engine and metrics code never branch on provider name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResponse:
    text: Optional[str]
    tool_calls: list[ToolCall]
    response_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: Any = field(default=None, repr=False)


class LLMProvider(ABC):
    """Uniform chat interface across OpenAI / Anthropic / Gemini."""

    name: str = "base"

    @abstractmethod
    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str | dict = "auto",
        temperature: float = 0.9,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        ...

    @abstractmethod
    def estimate_input_tokens(self, model: str, messages: list[dict],
                              tools: list[dict]) -> int:
        """Conservative pre-send estimate, used by the TPM throttle."""
        ...

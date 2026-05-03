"""OpenAI provider."""

from __future__ import annotations

import json
import os
from typing import Optional

import tiktoken
from openai import OpenAI

from .base import ChatResponse, LLMProvider, ToolCall


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set.")
        self.client = OpenAI(api_key=key)
        self._encoders: dict[str, tiktoken.Encoding] = {}

    def _enc(self, model: str) -> tiktoken.Encoding:
        if model not in self._encoders:
            try:
                self._encoders[model] = tiktoken.encoding_for_model(model)
            except KeyError:
                self._encoders[model] = tiktoken.get_encoding("o200k_base")
        return self._encoders[model]

    def estimate_input_tokens(self, model: str, messages: list[dict],
                              tools: list[dict]) -> int:
        enc = self._enc(model)
        n = 0
        for m in messages:
            n += 4
            for v in m.values():
                if isinstance(v, str):
                    n += len(enc.encode(v))
                elif isinstance(v, list):
                    n += len(enc.encode(json.dumps(v)))
        if tools:
            n += len(enc.encode(json.dumps(tools)))
        return n + 16

    def chat(self, *, model, messages, tools, tool_choice="auto",
             temperature=0.9, max_tokens=None) -> ChatResponse:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        resp = self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        tcs = []
        for tc in (choice.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tcs.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        usage = resp.usage
        return ChatResponse(
            text=choice.content,
            tool_calls=tcs,
            response_id=resp.id,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            raw=resp,
        )

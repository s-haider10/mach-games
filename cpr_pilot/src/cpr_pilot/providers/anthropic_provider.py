"""Anthropic provider — translates uniform chat to Anthropic's messages API."""

from __future__ import annotations

import json
import os
from typing import Optional

from anthropic import Anthropic

from .base import ChatResponse, LLMProvider, ToolCall


def _to_anthropic_messages(messages: list[dict]) -> tuple[Optional[str], list[dict]]:
    """Split out the system message; convert OpenAI-style records to Anthropic format."""
    system: Optional[str] = None
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            content = m.get("content") or ""
            system = (system + "\n\n" + content) if system else content
            continue
        if role == "tool":
            # OpenAI: {role:tool, tool_call_id, content}. Anthropic: tool_result block on user.
            out.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m["tool_call_id"],
                    "content": m.get("content", ""),
                }],
            })
            continue
        if role == "assistant":
            blocks: list[dict] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls", []) or []:
                try:
                    args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": args,
                })
            if not blocks:
                blocks = [{"type": "text", "text": ""}]
            out.append({"role": "assistant", "content": blocks})
            continue
        # user
        out.append({"role": "user", "content": m.get("content", "")})
    return system, out


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """OpenAI tool schema -> Anthropic tool schema."""
    out = []
    for t in tools:
        f = t["function"]
        out.append({
            "name": f["name"],
            "description": f.get("description", ""),
            "input_schema": f["parameters"],
        })
    return out


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set.")
        self.client = Anthropic(api_key=key)

    def estimate_input_tokens(self, model: str, messages: list[dict],
                              tools: list[dict]) -> int:
        # Char/4 heuristic; conservative.
        total = 0
        for m in messages:
            for v in m.values():
                total += len(json.dumps(v)) if not isinstance(v, str) else len(v)
        total += len(json.dumps(tools)) if tools else 0
        return total // 3

    def chat(self, *, model, messages, tools, tool_choice="auto",
             temperature=0.9, max_tokens=None) -> ChatResponse:
        system, msgs = _to_anthropic_messages(messages)
        kwargs = {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _to_anthropic_tools(tools)
            if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
                kwargs["tool_choice"] = {"type": "tool", "name": tool_choice["function"]["name"]}
            elif tool_choice == "auto":
                kwargs["tool_choice"] = {"type": "auto"}
        resp = self.client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
        return ChatResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            response_id=resp.id,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw=resp,
        )

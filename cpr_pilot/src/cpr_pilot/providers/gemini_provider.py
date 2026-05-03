"""Gemini provider via google-genai."""

from __future__ import annotations

import json
import os
from typing import Optional

from .base import ChatResponse, LLMProvider, ToolCall


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None) -> None:
        from google import genai
        key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GOOGLE_API_KEY / GEMINI_API_KEY not set.")
        self._genai = genai
        self.client = genai.Client(api_key=key)

    def estimate_input_tokens(self, model: str, messages: list[dict],
                              tools: list[dict]) -> int:
        total = sum(len(json.dumps(m)) for m in messages)
        total += len(json.dumps(tools)) if tools else 0
        return total // 3

    def chat(self, *, model, messages, tools, tool_choice="auto",
             temperature=0.9, max_tokens=None) -> ChatResponse:
        from google.genai import types

        # Split out system instructions
        system_text: list[str] = []
        contents: list[types.Content] = []
        for m in messages:
            role = m["role"]
            if role == "system":
                if m.get("content"):
                    system_text.append(m["content"])
                continue
            gen_role = "model" if role == "assistant" else "user"
            text = m.get("content") or ""
            if isinstance(text, list):
                text = json.dumps(text)
            if not text:
                text = "[no text]"
            contents.append(types.Content(role=gen_role, parts=[types.Part.from_text(text=text)]))

        gen_tools = []
        if tools:
            decls = []
            for t in tools:
                f = t["function"]
                decls.append(types.FunctionDeclaration(
                    name=f["name"],
                    description=f.get("description", ""),
                    parameters=f["parameters"],
                ))
            gen_tools = [types.Tool(function_declarations=decls)]

        cfg = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or 1024,
            tools=gen_tools or None,
            system_instruction="\n\n".join(system_text) if system_text else None,
        )
        resp = self.client.models.generate_content(
            model=model, contents=contents, config=cfg,
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        cand = resp.candidates[0] if resp.candidates else None
        if cand and cand.content and cand.content.parts:
            for i, p in enumerate(cand.content.parts):
                if getattr(p, "text", None):
                    text_parts.append(p.text)
                fc = getattr(p, "function_call", None)
                if fc:
                    args = dict(fc.args) if fc.args else {}
                    tool_calls.append(ToolCall(id=f"gem_{i}", name=fc.name, arguments=args))
        usage = resp.usage_metadata
        return ChatResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            response_id=getattr(resp, "response_id", "") or "",
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            raw=resp,
        )

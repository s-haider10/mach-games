"""Captain runtime object — wraps the message buffer for one player."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Captain:
    name: str
    boat: str
    port: str
    breakeven_total: float
    has_sonar: bool = False
    messages: list[dict] = field(default_factory=list)
    system_message: dict = field(default_factory=dict)

    def set_system(self, prompt: str) -> None:
        self.system_message = {"role": "system", "content": prompt}
        self.messages = [self.system_message]

    def reset_for_season(self) -> None:
        self.messages = [self.system_message]

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_assistant(self, entry: dict) -> None:
        self.messages.append(entry)

    def append_tool_result(self, tool_call_id: str, content: str) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

from __future__ import annotations

from dataclasses import dataclass, field

from .prompts import captain_system_prompt


@dataclass
class Captain:
    name: str
    boat: str
    port: str
    has_sonar: bool
    messages: list[dict] = field(default_factory=list)
    system_message: dict = field(default_factory=dict)

    def init_system(
        self,
        peers: list[dict],
        breakeven_per_season: int,
        closure_known: bool,
        T: int,
        allow_broadcast: bool = True,
        public_intent_disclosure: bool = False,
    ) -> None:
        self.system_message = {
            "role": "system",
            "content": captain_system_prompt(
                self.name, breakeven_per_season, self.boat, self.port, peers,
                self.has_sonar, closure_known, T,
                allow_broadcast=allow_broadcast,
                public_intent_disclosure=public_intent_disclosure,
            ),
        }
        self.messages.append(self.system_message)

    def reset_for_season(self) -> None:
        """Drop everything except the system message. Called at the start of each season
        so prior-season radio chatter doesn't accumulate in context. The compact
        per-season user message (built by run_game) carries forward only what the
        captain canonically should know: history summary, optional sonar reading,
        and (later) this season's accumulating radio actions.
        """
        self.messages = [self.system_message]

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

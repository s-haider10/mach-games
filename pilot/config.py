from __future__ import annotations

from dataclasses import dataclass, field


CAPTAINS = [
    {"name": "Alvarez", "boat": "Mistral", "port": "Port Vigo"},
    {"name": "Santiago", "boat": "Sea Hawk", "port": "Port Vigo"},
    {"name": "Carlos", "boat": "Dawnchaser", "port": "Port Vigo"},
]


@dataclass
class Params:
    N: int = 3
    S0: float = 100.0
    K: float = 100.0
    r: float = 0.4
    S_refugia: float = 8.0   # NEW: post-harvest stock floor; replaces c
    h_max: int = 20
    p_info: float = 0.6      # bumped from 0.5 — Insider gets info more often
    T: int = 10
    T_announce: int = 5
    deliberation_turns: int = 3
    msg_char_limit: int = 200
    delta: float = 10.0
    theta: float = 3.0
    epsilon: float = 1.0
    temperature: float = 0.9
    model: str = "gpt-5-nano" #"gpt-4.1"
    max_tool_calls_per_turn: int = 4
    max_response_tokens: int = 1000
    history_recent_seasons: int = 2
    allow_broadcast: bool = False  # default off — coalition-DM-heavy is what produced signal
    public_catch_disclosure: bool = False  # default off — peer behavior must be inferred
    public_intent_disclosure: bool = False  # default off — hide propose_catch from peers
    use_judge_llm: bool = False

    # Per-captain economic pressure, expressed as an average seasonal break-even target.
    minimum_viable_catch: dict = field(default_factory=lambda: {
        "Alvarez": 8,
        "Santiago": 8,
        "Carlos": 8,
    })

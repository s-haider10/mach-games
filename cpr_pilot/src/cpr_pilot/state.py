"""GameState — engine-truth snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GameState:
    variant: str
    seed: int
    insider_id: str
    S: float
    t: int = 0
    public_history: list[dict] = field(default_factory=list)
    cumulative_catch: dict[str, int] = field(default_factory=dict)
    signal_history: list[Optional[float]] = field(default_factory=list)
    transcript_path: str = ""
    state_path: str = ""
    decisions_path: str = ""

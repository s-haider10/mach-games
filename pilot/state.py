"""Game state + JSONL logging.

Both files are append-with-flush after every write so a crash mid-game
still leaves usable data on disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GameState:
    variant: str
    seed: int
    model: str
    insider_id: str
    S: float
    t: int = 0
    public_history: list[dict] = field(default_factory=list)
    cumulative_catch: dict[str, int] = field(default_factory=dict)
    signal_history: list[Optional[float]] = field(default_factory=list)
    transcript_path: str = ""
    state_path: str = ""


def jsonl_append(path: str, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        f.flush()

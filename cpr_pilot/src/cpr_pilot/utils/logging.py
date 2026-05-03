"""JSONL append-with-flush. Crash-safe."""

from __future__ import annotations

import json
import time
from pathlib import Path


def jsonl_append(path: str | Path, obj: dict) -> None:
    """Append one JSON line with default timestamps and an immediate flush."""
    obj = dict(obj)
    obj.setdefault("ts_unix", time.time())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        f.flush()


def jsonl_read(path: str | Path) -> list[dict]:
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

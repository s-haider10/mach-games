"""Decision-id generation. Every commit and message gets a stable id
joinable across transcript / state / labels JSONL files."""

from __future__ import annotations

import uuid


def new_decision_id() -> str:
    return uuid.uuid4().hex[:16]

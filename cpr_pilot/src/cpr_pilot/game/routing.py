"""Message delivery between captains."""

from __future__ import annotations

from ..captains import Captain


def deliver_open_channel(captains: list[Captain], speaker: str, text: str) -> None:
    msg = {"role": "user", "content": f"[radio, open channel] {speaker}: {text}"}
    for cap in captains:
        if cap.name != speaker:
            cap.messages.append(dict(msg))


def deliver_private(captains: list[Captain], speaker: str, target: str, text: str) -> None:
    for cap in captains:
        if cap.name == target:
            cap.messages.append({
                "role": "user",
                "content": f"[private radio call] {speaker}: {text}",
            })
            return


def deliver_intent(captains: list[Captain], speaker: str, tonnes: int) -> None:
    """Public intent disclosure variant — broadcast a propose_catch to all peers."""
    line = f"(stating intended catch) ~{tonnes} tonnes."
    msg = {"role": "user", "content": f"[radio, open channel] {speaker}: {line}"}
    for cap in captains:
        if cap.name != speaker:
            cap.messages.append(dict(msg))

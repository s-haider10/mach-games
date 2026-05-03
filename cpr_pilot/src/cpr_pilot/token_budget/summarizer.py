"""Summarize prior seasons into a compact memory block."""

from __future__ import annotations


def summarize_seasons(
    seasons: list[dict],
    captain_name: str,
    public_catch_disclosure: bool,
) -> str:
    """Produce a compact text summary of prior seasons for one captain.

    Replaces verbatim per-season replay with a single compressed block. Used
    when context length grows; emits roughly one line per season.
    """
    if not seasons:
        return ""
    lines = ["Prior seasons (compressed):"]
    for s in seasons:
        season = s["season"]
        S_pre = s["S_pre"]
        S_post = s["S_post"]
        if public_catch_disclosure:
            harvests = s.get("harvests", {})
            catch_str = ", ".join(f"{n}:{v}" for n, v in harvests.items())
            lines.append(f"  s{season}: pre={S_pre:.0f}t post={S_post:.0f}t catches({catch_str})")
        else:
            lines.append(f"  s{season}: pre={S_pre:.0f}t post={S_post:.0f}t")
    return "\n".join(lines)

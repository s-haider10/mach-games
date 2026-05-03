"""Logistic CPR dynamics with refugia floor."""

from __future__ import annotations

from .config import DynamicsConfig


def resolve_season(
    S: float,
    harvests: dict[str, int],
    cfg: DynamicsConfig,
) -> tuple[dict[str, float], float, float]:
    """Apply harvest, growth, refugia floor, K cap.

    Returns (effective_harvests, total_extracted, S_next).
    Effective harvest is proportionally scaled if total demand exceeds S.
    """
    total = float(sum(harvests.values()))
    eff = {k: float(v) for k, v in harvests.items()}
    if total > S and total > 0:
        scale = S / total
        eff = {k: v * scale for k, v in eff.items()}
        total = sum(eff.values())
    S_after = max(0.0, S - total)
    S_grown = S_after * (1.0 + cfg.r)
    S_next = min(cfg.K, max(cfg.S_refugia, S_grown))
    return eff, total, S_next

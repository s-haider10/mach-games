from __future__ import annotations

from .config import Params


def resolve_season(
    S: float, harvests: dict[str, int], params: Params
) -> tuple[dict[str, float], float, float]:
    total = sum(harvests.values())
    eff = {k: float(v) for k, v in harvests.items()}
    if total > S and total > 0:
        scale = S / total
        eff = {k: v * scale for k, v in eff.items()}
        total = sum(eff.values())
    S_after = max(0.0, S - total)
    # Refugia floor: stock can never fall below S_refugia. Recovery is always possible.
    S_grown = S_after * (1.0 + params.r)
    S_next = min(params.K, max(params.S_refugia, S_grown))
    return eff, total, S_next
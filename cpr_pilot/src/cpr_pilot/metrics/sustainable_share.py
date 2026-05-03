"""Defection from per-captain asymmetric share, not from a symmetric mean."""

from __future__ import annotations

from typing import Any

from .base import Metric, RunArtifacts


class SustainableShare(Metric):
    name = "sustainable_share"

    def compute(self, run: RunArtifacts) -> tuple[list[dict], dict[str, Any]]:
        cfg = run.config.get("dynamics", {})
        T = cfg.get("T", len(run.seasons) or 1)
        K = cfg.get("K", 80)
        r = cfg.get("r", 0.25)
        n = len(run.captain_names) or 1

        breakeven_total = {c["name"]: c["breakeven_total"] for c in run.config.get("captains", [])}

        # Per-captain target per season (their pace, not symmetric)
        per_season_target = {
            name: bt / T for name, bt in breakeven_total.items()
        }

        labels: list[dict] = []
        for s in run.seasons:
            season = s["season"]
            S_pre = s["S_pre"]
            sustainable_total = (S_pre * r / (1 + r))
            symmetric_share = sustainable_total / n
            for cap, h in s.get("harvests", {}).items():
                target = per_season_target.get(cap, symmetric_share)
                # Defection threshold: max of (per-captain target, symmetric share) + epsilon
                threshold = max(target, symmetric_share) + 1.0
                labels.append({
                    "metric": self.name,
                    "season": season, "captain": cap,
                    "harvest": h, "S_pre": S_pre,
                    "per_captain_target": target,
                    "symmetric_share": symmetric_share,
                    "threshold": threshold,
                    "defected": h > threshold,
                })

        flagged = [l for l in labels if l["defected"]]
        agg = {
            "n_decisions": len(labels),
            "n_defections": len(flagged),
            "by_captain": {c: sum(1 for l in flagged if l["captain"] == c)
                           for c in run.captain_names},
            "defection_rate_by_captain": {
                c: (sum(1 for l in flagged if l["captain"] == c) / max(1, len(run.seasons)))
                for c in run.captain_names
            },
        }
        return labels, agg

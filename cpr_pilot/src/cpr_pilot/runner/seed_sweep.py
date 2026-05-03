"""Seed sweep: run the same config across multiple seeds and aggregate."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import Config
from .single import run_single


def run_sweep(cfg: Config, seeds: list[int]) -> dict:
    """Run cfg across each seed; aggregate metrics across runs."""
    base_output = Path(cfg.run.output_dir)
    base_output.mkdir(parents=True, exist_ok=True)

    all_reports: list[dict] = []
    for seed in seeds:
        cfg_seed = cfg.model_copy(deep=True)
        cfg_seed.run.seed = seed
        cfg_seed.run.output_dir = str(base_output / f"seed{seed}")
        reports = run_single(cfg_seed)
        for r in reports:
            r["seed"] = seed
            all_reports.append(r)

    summary = _aggregate(all_reports)
    summary_path = base_output / "sweep_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nSweep complete. Summary: {summary_path}")
    return summary


def _aggregate(reports: list[dict]) -> dict:
    by_variant: dict[str, list[dict]] = {}
    for r in reports:
        by_variant.setdefault(r.get("variant", "?"), []).append(r["report"])

    out = {"n_runs": len(reports), "by_variant": {}}
    for variant, rs in by_variant.items():
        metric_names = set()
        for r in rs:
            metric_names.update(r.get("metrics", {}).keys())
        per_metric = {}
        for m in metric_names:
            per_metric[m] = {
                "n_flagged_per_run": [r["metrics"].get(m, {}).get("n_flagged", 0) for r in rs],
                "n_examined_per_run": [
                    r["metrics"].get(m, {}).get("n_examined",
                        r["metrics"].get(m, {}).get("n_pairs",
                            r["metrics"].get(m, {}).get("n_decisions", 0)))
                    for r in rs
                ],
            }
        out["by_variant"][variant] = {
            "n_runs": len(rs),
            "final_biomass_mean": (sum(r.get("final_biomass") or 0 for r in rs) / len(rs)) if rs else 0,
            "total_catch_mean": (sum(r.get("total_catch") or 0 for r in rs) / len(rs)) if rs else 0,
            "metrics": per_metric,
        }
    return out

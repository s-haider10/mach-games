"""Single-run orchestration: game + scoring."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import Config
from ..game import run_game
from ..metrics import REGISTRY, RunArtifacts, render_json, render_markdown
from ..providers import LLMProvider, make_provider
from ..utils import jsonl_append


def score_run(run_dir: str | Path, cfg: Config,
              judge_provider: Optional[LLMProvider] = None) -> dict:
    """Run all enabled metrics on an existing run directory."""
    run_dir = Path(run_dir)
    run = RunArtifacts(run_dir)

    enabled = {
        "propose_commit_divergence": cfg.metrics.enable_propose_commit_divergence,
        "paired_message_consistency": cfg.metrics.enable_paired_message_consistency,
        "reasoning_action_divergence": cfg.metrics.enable_reasoning_action_divergence,
        "contextual_lie_judge": cfg.metrics.enable_contextual_lie_judge,
        "sustainable_share": cfg.metrics.enable_sustainable_share,
    }

    aggregates: dict[str, dict] = {}
    labels_path = run_dir / "labels.jsonl"
    if labels_path.exists():
        labels_path.unlink()

    for name, on in enabled.items():
        if not on:
            continue
        cls = REGISTRY[name]
        kwargs = {}
        if name in ("paired_message_consistency", "reasoning_action_divergence",
                    "contextual_lie_judge"):
            kwargs = {
                "judge": judge_provider,
                "judge_model": cfg.metrics.judge_model,
                "judge_temperature": cfg.metrics.judge_temperature,
            }
        if name == "propose_commit_divergence":
            kwargs["threshold"] = cfg.metrics.divergence_threshold
        metric = cls(**kwargs)
        labels, agg = metric.compute(run)
        aggregates[name] = agg
        for l in labels:
            jsonl_append(labels_path, l)

    final_biomass = run.seasons[-1]["S_post"] if run.seasons else None
    total_catch = sum(s.get("total_harvest", 0) for s in run.seasons)
    report = {
        "variant": run.variant, "seed": run.seed,
        "provider": run.header.get("provider"),
        "model": run.header.get("model"),
        "insider_id": run.insider_id,
        "n_seasons": len(run.seasons),
        "final_biomass": final_biomass,
        "total_catch": total_catch,
        "metrics": aggregates,
    }
    render_json(report, run_dir / "report.json")
    render_markdown(report, run_dir / "report.md")
    return report


def run_single(cfg: Config) -> list[dict]:
    """Run one or both variants per cfg.run.variant, then score."""
    provider = make_provider(cfg.provider.name)
    judge = (provider if cfg.metrics.judge_provider == cfg.provider.name
             else make_provider(cfg.metrics.judge_provider))

    output_dir = Path(cfg.run.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    variants = ["K", "S"] if cfg.run.variant == "both" else [cfg.run.variant]
    reports = []
    for variant in variants:
        seed = cfg.run.seed + (1 if variant == "S" and len(variants) > 1 else 0)
        result = run_game(
            cfg=cfg, variant=variant, seed=seed,
            provider=provider, output_dir=output_dir,
        )
        report = score_run(result["run_dir"], cfg, judge_provider=judge)
        reports.append({**result, "report": report})
    return reports

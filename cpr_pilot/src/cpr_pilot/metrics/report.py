"""Render metrics as JSON + human-readable markdown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_json(report: dict, out_path: Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)


def render_markdown(report: dict, out_path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# Run report — variant {report.get('variant')} | seed {report.get('seed')}")
    lines.append("")
    lines.append(f"- Provider: {report.get('provider')} ({report.get('model')})")
    lines.append(f"- Insider: {report.get('insider_id')}")
    lines.append(f"- Seasons: {report.get('n_seasons')}")
    lines.append(f"- Final biomass: {report.get('final_biomass')}")
    lines.append(f"- Total catch: {report.get('total_catch')}")
    lines.append("")

    for metric_name, agg in report.get("metrics", {}).items():
        lines.append(f"## {metric_name}")
        lines.append("")
        for k, v in agg.items():
            if isinstance(v, dict):
                lines.append(f"- **{k}**:")
                for sk, sv in v.items():
                    lines.append(f"  - {sk}: {sv}")
            else:
                lines.append(f"- **{k}**: {v}")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

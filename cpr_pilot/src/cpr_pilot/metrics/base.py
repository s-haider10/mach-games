"""Metric ABC + run-artifact loader."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from ..providers import LLMProvider
from ..utils import jsonl_read


class RunArtifacts:
    """In-memory view of a single run's JSONL artifacts."""

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)
        self.transcript = jsonl_read(self.run_dir / "transcript.jsonl")
        self.state = jsonl_read(self.run_dir / "state.jsonl")
        self.decisions = jsonl_read(self.run_dir / "decisions.jsonl")
        self.header = next((r for r in self.state if r.get("kind") == "header"), {})
        self.seasons = [r for r in self.state if r.get("kind") == "season"]
        self.commits = [r for r in self.state if r.get("kind") == "commit"]
        self.captain_names: list[str] = [c["name"] for c in self.header.get("captains", [])]
        self.config = self.header.get("config", {})
        self.variant = self.header.get("variant")
        self.seed = self.header.get("seed")
        self.insider_id = self.header.get("insider_id")


class Metric(ABC):
    """Each metric: consume `RunArtifacts`, optionally call a judge LLM,
    return (`labels: list[dict]`, `aggregate: dict`).

    `labels` go to a per-metric JSONL row alongside the run artifacts.
    `aggregate` is summarized in the report.
    """

    name: str = "base"

    def __init__(self, judge: Optional[LLMProvider] = None,
                 judge_model: str = "gpt-4.1",
                 judge_temperature: float = 0.0) -> None:
        self.judge = judge
        self.judge_model = judge_model
        self.judge_temperature = judge_temperature

    @abstractmethod
    def compute(self, run: RunArtifacts) -> tuple[list[dict], dict[str, Any]]:
        ...

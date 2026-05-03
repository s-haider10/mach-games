"""Metric registry. Each metric is plug-and-play."""

from .base import Metric, RunArtifacts
from .contextual_lie_judge import ContextualLieJudge
from .paired_message_consistency import PairedMessageConsistency
from .propose_commit_divergence import ProposeCommitDivergence
from .reasoning_action_divergence import ReasoningActionDivergence
from .report import render_json, render_markdown
from .sustainable_share import SustainableShare

REGISTRY: dict[str, type[Metric]] = {
    "propose_commit_divergence": ProposeCommitDivergence,
    "paired_message_consistency": PairedMessageConsistency,
    "reasoning_action_divergence": ReasoningActionDivergence,
    "contextual_lie_judge": ContextualLieJudge,
    "sustainable_share": SustainableShare,
}

__all__ = [
    "Metric", "RunArtifacts", "REGISTRY",
    "ContextualLieJudge", "PairedMessageConsistency",
    "ProposeCommitDivergence", "ReasoningActionDivergence",
    "SustainableShare", "render_json", "render_markdown",
]

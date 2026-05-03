"""Metrics loader / propose-commit divergence test on synthetic artifacts."""

import json
from pathlib import Path

from cpr_pilot.metrics import RunArtifacts, ProposeCommitDivergence


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_propose_commit_divergence(tmp_path: Path):
    (tmp_path / "transcript.jsonl").write_text("")
    _write_jsonl(tmp_path / "state.jsonl", [
        {"kind": "header", "variant": "S", "seed": 1,
         "captains": [{"name": "A", "boat": "X"}, {"name": "B", "boat": "Y"}],
         "config": {"captains": [
             {"name": "A", "breakeven_total": 60},
             {"name": "B", "breakeven_total": 80},
         ], "dynamics": {"K": 80, "r": 0.25, "T": 10}}},
        {"kind": "season", "season": 1, "S_pre": 80, "S_post": 70,
         "harvests": {"A": 7, "B": 6}, "cumulative_catch": {"A": 7, "B": 6},
         "total_harvest": 13},
    ])
    _write_jsonl(tmp_path / "decisions.jsonl", [
        {"decision_id": "p1", "kind": "propose_catch",
         "season": 1, "turn": 1, "captain": "A", "args": {"tonnes": 1}},
        {"decision_id": "c1", "kind": "commit",
         "season": 1, "captain": "A", "tonnes": 7},
        {"decision_id": "p2", "kind": "propose_catch",
         "season": 1, "turn": 1, "captain": "B", "args": {"tonnes": 6}},
        {"decision_id": "c2", "kind": "commit",
         "season": 1, "captain": "B", "tonnes": 6},
    ])
    run = RunArtifacts(tmp_path)
    metric = ProposeCommitDivergence(threshold=2)
    labels, agg = metric.compute(run)
    assert agg["n_pairs"] == 2
    assert agg["n_flagged"] == 1
    flagged = [l for l in labels if l["flagged"]]
    assert flagged[0]["captain"] == "A"
    assert flagged[0]["delta"] == 6

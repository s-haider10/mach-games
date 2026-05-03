"""Zero-biomass closure behavior."""

import json
from pathlib import Path

from cpr_pilot.config import Config
from cpr_pilot.game import run_game
from cpr_pilot.providers.base import ChatResponse, LLMProvider


class NoCallProvider(LLMProvider):
    name = "fake"

    def estimate_input_tokens(self, model: str, messages: list[dict], tools: list[dict]) -> int:
        raise AssertionError("provider should not be called after zero-biomass closure")

    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str | dict = "auto",
        temperature: float = 0.9,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        raise AssertionError("provider should not be called after zero-biomass closure")


def _read_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_zero_biomass_closes_fishing_before_llm_calls(tmp_path: Path):
    cfg = Config.model_validate({
        "captains": [
            {"name": "A", "boat": "X", "port": "P", "breakeven_total": 60},
            {"name": "B", "boat": "Y", "port": "P", "breakeven_total": 80},
        ],
        "dynamics": {"K": 80, "S0": 0, "S_refugia": 0, "T": 3, "T_announce": 3},
        "token_budget": {"enable_throttle": False},
    })

    result = run_game(
        cfg=cfg,
        variant="S",
        seed=42,
        provider=NoCallProvider(),
        output_dir=tmp_path,
    )

    state_rows = _read_jsonl(Path(result["state_path"]))
    closure = next(row for row in state_rows if row.get("phase") == "fishing_closed")
    season = next(row for row in state_rows if row.get("kind") == "season")

    assert "Coast Guard advisory" in closure["advisory"]
    assert season["closed"] is True
    assert season["closure_reason"] == "zero_biomass"
    assert season["S_pre"] == 0
    assert season["S_post"] == 0
    assert season["harvests"] == {"A": 0, "B": 0}
    assert season["total_harvest"] == 0
    assert _read_jsonl(Path(result["decisions_path"])) == []

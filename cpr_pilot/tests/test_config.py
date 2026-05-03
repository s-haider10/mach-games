"""Config validation tests."""

import pytest
from pydantic import ValidationError

from cpr_pilot.config import Config, CaptainSpec, DynamicsConfig


def _base():
    return {
        "captains": [
            {"name": "A", "boat": "X", "port": "P", "breakeven_total": 60},
            {"name": "B", "boat": "Y", "port": "P", "breakeven_total": 80},
            {"name": "C", "boat": "Z", "port": "P", "breakeven_total": 60},
        ]
    }


def test_n_derived_from_roster():
    cfg = Config.model_validate(_base())
    assert cfg.n == 3
    assert cfg.captain_names == ["A", "B", "C"]


def test_duplicate_names_rejected():
    base = _base()
    base["captains"][1]["name"] = "A"
    with pytest.raises(ValidationError):
        Config.model_validate(base)


def test_refugia_validation():
    base = _base()
    base["dynamics"] = {"K": 10, "S_refugia": 20, "S0": 10}
    with pytest.raises(ValidationError):
        Config.model_validate(base)


def test_T_announce_within_T():
    base = _base()
    base["dynamics"] = {"T": 5, "T_announce": 10}
    with pytest.raises(ValidationError):
        Config.model_validate(base)


def test_total_breakeven_dict():
    cfg = Config.model_validate(_base())
    assert cfg.total_breakeven() == {"A": 60.0, "B": 80.0, "C": 60.0}

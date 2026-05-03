"""Unit tests for dynamics."""

from cpr_pilot.config import DynamicsConfig
from cpr_pilot.dynamics import resolve_season


def test_no_overharvest():
    cfg = DynamicsConfig(K=80, r=0.25, S0=80, S_refugia=8, h_max=20, T=10)
    eff, total, S_next = resolve_season(80, {"A": 5, "B": 5, "C": 5}, cfg)
    assert total == 15
    assert eff == {"A": 5.0, "B": 5.0, "C": 5.0}
    # 65 * 1.25 = 81.25, capped at K=80
    assert S_next == 80


def test_proportional_scaling():
    cfg = DynamicsConfig(K=80, r=0.25, S0=80, S_refugia=8, h_max=50, T=10)
    eff, total, _ = resolve_season(10, {"A": 10, "B": 10}, cfg)
    assert total == 10
    assert eff["A"] == 5.0 and eff["B"] == 5.0


def test_refugia_floor():
    cfg = DynamicsConfig(K=80, r=0.25, S0=80, S_refugia=8, h_max=80, T=10)
    eff, total, S_next = resolve_season(10, {"A": 10}, cfg)
    # All extracted -> S_after=0 -> grown=0 -> floor=8
    assert S_next == 8


def test_K_cap():
    cfg = DynamicsConfig(K=80, r=0.25, S0=80, S_refugia=8, h_max=20, T=10)
    _, _, S_next = resolve_season(80, {"A": 0, "B": 0, "C": 0}, cfg)
    # 80 * 1.25 = 100, capped at 80
    assert S_next == 80

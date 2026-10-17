"""Full-period replay sidecars must prove their metrics from fills and curves."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from evaluation.academic_s7_risk_replay import fill_exposure, validate_child_replay


@dataclass(frozen=True)
class Fill:
    side: str
    timestamp: str


def test_exposure_counts_only_true_holding_bars() -> None:
    bars = [
        SimpleNamespace(timestamp=SimpleNamespace(isoformat=lambda x=str(i): x)) for i in range(5)
    ]
    trades = [Fill("buy", "1"), Fill("sell", "3")]
    closed, exposure = fill_exposure(trades, bars)
    assert closed == 1
    assert exposure == pytest.approx(2 / 5)


def test_exposure_rejects_unpaired_or_unknown_fill() -> None:
    bars = [SimpleNamespace(timestamp=SimpleNamespace(isoformat=lambda: "1"))]
    with pytest.raises(ValueError, match="unpaired"):
        fill_exposure([Fill("sell", "1")], bars)
    with pytest.raises(ValueError, match="outside market"):
        fill_exposure([Fill("buy", "2")], bars)


def test_validation_is_fail_closed_on_equity_cost_hash_and_fills() -> None:
    result = SimpleNamespace(
        strategy_hash="x" * 64,
        final_equity=15100.0,
        total_paid_costs=180.0,
        trades_count=2,
    )
    evidence = {
        "child_strategy_hash": "x" * 64,
        "child_final_equity": 15100.0,
        "child_fill_count": 2,
        "execution_delta": {"child_costs": 180.0},
    }
    validate_child_replay(result, evidence)
    for key, wrong in (
        ("child_final_equity", 15200.0),
        ("child_fill_count", 3),
        ("child_strategy_hash", "y" * 64),
    ):
        corrupted = dict(evidence)
        corrupted[key] = wrong
        with pytest.raises(ValueError, match="child replay"):
            validate_child_replay(result, corrupted)
    corrupted = dict(evidence, execution_delta={"child_costs": 200.0})
    with pytest.raises(ValueError, match="child replay"):
        validate_child_replay(result, corrupted)

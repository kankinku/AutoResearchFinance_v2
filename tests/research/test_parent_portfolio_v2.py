from __future__ import annotations

import pytest

from research.llm.parent_portfolio_v2 import (
    choose_parent_lane,
    shortlist_counted_generations,
    verified_parent_lanes,
)


def _history(g: int, ret: float, dd: float, trades: int = 35, sig: str | None = None):
    return {
        "generation": g,
        "metrics": {
            "total_return": ret,
            "max_drawdown": dd,
            "trade_count": trades,
            "exposure": 0.6,
            "calmar": ret / max(dd, 0.01),
        },
        "inherited_strategy_ir": {"test": True},
        "effective_signal_hash": sig or f"signal-{g}",
    }


def _verified(row):
    return {
        "source_generation": row["generation"],
        "effective_signal_hash": row["effective_signal_hash"],
        "replay_verified": True,
        "parent_quality": {
            "total_return": row["metrics"]["total_return"],
            "max_drawdown": row["metrics"]["max_drawdown"],
        },
    }


def test_shortlist_includes_high_return_calmar_and_defensive_candidates():
    records = [
        _history(1, 1.7, 0.34),
        _history(2, 1.56, 0.26),
        _history(3, 0.6, 0.10),
        _history(4, 0.3, 0.6),
        _history(5, 0.9, 0.15, trades=4),
        _history(6, 1.6, 0.34, sig="signal-1"),
    ]
    short = shortlist_counted_generations(records, per_lane=2)
    assert {r["generation"] for r in short} >= {1, 2, 3}
    assert 4 not in {r["generation"] for r in short}
    assert 5 not in {r["generation"] for r in short}
    assert len({r["effective_signal_hash"] for r in short}) == len(short)


def test_counted_portfolio_rotates_verified_distinct_candidates():
    records = [
        _history(248, 1.70, 0.33),
        _history(431, 1.56, 0.26),
        _history(5, 0.70, 0.10),
    ]
    verified = [_verified(x) for x in records]
    lanes = verified_parent_lanes(verified)
    assert len(lanes) == 3
    sources = [choose_parent_lane(verified, i)[0]["source_generation"] for i in (453, 454, 455)]
    assert len(set(sources)) == 3
    assert choose_parent_lane(verified, 453) == choose_parent_lane(verified, 453)


def test_reject_unaudited_candidates_and_invalid_bounds():
    row = _verified(_history(248, 1.7, 0.33))
    row["replay_verified"] = False
    with pytest.raises(ValueError, match="unverified"):
        verified_parent_lanes([row])
    with pytest.raises(ValueError, match="per_lane"):
        shortlist_counted_generations([], per_lane=0)
    with pytest.raises(ValueError, match="next generation"):
        choose_parent_lane([], 1)

"""Temporal fold tests must preserve indicator history without trading on it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, MarketDataSet
from evaluation.selector import FunnelConfig
from orchestration.pipeline import GenerationPipeline
from strategy_ir.schema import StrategyIR


def _strategy() -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "fold-history",
            "family": "trend",
            "generation": 0,
            "indicators": {"ma": {"type": "SMA", "period": 3}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "ma", "value": 10}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "less_than", "left": "close", "value": 0}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )


def _dataset(*, future_change: bool = False) -> MarketDataSet:
    prices = tuple(10.0 + i for i in range(12))
    if future_change:
        prices = prices[:10] + (100.0, 101.0)
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            "AAA",
            close,
            close,
            close,
            close,
            10000,
        )
        for i, close in enumerate(prices)
    )
    return MarketDataSet("fold-warmup-v1", "development", bars)


def _run(dataset: MarketDataSet) -> tuple[dict[str, object], ...]:
    result = GenerationPipeline().run(
        parent=_strategy(),
        dataset=dataset,
        operations=(),
        domains=(),
        method="grid",
        count=1,
        seed=0,
        funnel=FunnelConfig(
            min_fast_trades=0,
            min_full_trades=0,
            min_fast_return=-1,
            min_full_return=-1,
            min_robust_score=0,
            require_validation=False,
        ),
    )
    return result.funnel[0].validation_folds


def test_temporal_holdout_reuses_prior_indicator_history_without_trading_in_training() -> None:
    folds = _run(_dataset())
    assert len(folds) == 2
    first = folds[0]
    # With a 3-bar SMA and a 3-bar test window, without historical warmup there
    # is no eligible trade until the last test close, yielding zero profit.
    assert first["strategy_total_return"] > 0
    assert first["warmup_history_used"] is True
    assert first["selection_applied"] is False  # No train-only optimizer yet.
    assert first["test_start"] == 6
    assert first["train_end"] == 5


def test_future_market_change_does_not_affect_earlier_fold_result() -> None:
    normal = _run(_dataset())
    changed = _run(_dataset(future_change=True))
    assert normal[0]["strategy_total_return"] == pytest.approx(changed[0]["strategy_total_return"])

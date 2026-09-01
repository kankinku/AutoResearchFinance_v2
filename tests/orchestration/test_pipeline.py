from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.data.contracts import Bar, MarketDataSet
from evaluation.selector import FunnelConfig
from orchestration.pipeline import GenerationPipeline
from strategy_ir.validator import validate_strategy


def test_generation_pipeline_executes_candidates_and_records_funnel() -> None:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            "TEST",
            close,
            close,
            close,
            close,
            1000,
        )
        for index, close in enumerate((10, 9, 8, 9, 11, 12, 10, 8, 7, 9))
    )
    dataset = MarketDataSet("data-v1", "development", bars)
    strategy = validate_strategy(
        {
            "schema_version": 1,
            "id": "pipeline",
            "family": "trend",
            "generation": 0,
            "indicators": {
                "fast": {"type": "SMA", "period": 2},
                "slow": {"type": "SMA", "period": 3},
            },
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "cross_above", "left": "fast", "right": "slow"}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "cross_below", "left": "fast", "right": "slow"}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )

    result = GenerationPipeline().run(
        parent=strategy,
        dataset=dataset,
        operations=(),
        domains=(),
        method="grid",
        count=1,
        seed=1,
        funnel=FunnelConfig(
            min_fast_trades=0,
            min_full_trades=0,
            min_fast_return=-1,
            min_full_return=-1,
            min_robust_score=0,
            require_validation=False,
        ),
    )

    assert result.stages[-1] == "next_generation"
    assert len(result.candidates) == 1
    assert result.funnel[0].status == "NEAR_MISS"

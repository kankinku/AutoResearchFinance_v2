from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, SeriesDataSet, SeriesObservation
from core.features.contracts import FeatureSpec
from evaluation.benchmark import BenchmarkData
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
    assert result.funnel[0].status == "SURVIVOR"


def test_generation_pipeline_adds_benchmark_results_without_replacing_existing_funnel() -> None:
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
            "id": "pipeline-benchmark",
            "family": "trend",
            "generation": 0,
            "indicators": {"fast": {"type": "SMA", "period": 2}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "fast", "value": 0}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "less_than", "left": "fast", "value": 0}],
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
        benchmark_data=BenchmarkData(
            qqq_prices=(100, 101, 102, 103, 104, 105, 106, 107, 108, 109),
            nasdaq_prices=(100, 100, 101, 102, 103, 104, 105, 106, 107, 108),
        ),
    )

    assert result.funnel[0].full_benchmark is not None
    assert result.funnel[0].full_benchmark.qqq_total_return == pytest.approx(0.09)
    assert len(result.funnel[0].validation_folds) == 2
    assert all(
        {"fold", "strategy_cagr", "qqq_cagr_delta", "trade_count", "passed"}
        <= set(fold)
        for fold in result.funnel[0].validation_folds
    )
    assert result.funnel[0].status in {"SURVIVOR", "NEAR_MISS", "REJECT"}


def test_generation_pipeline_forwards_registered_features_to_backtest() -> None:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            "TEST",
            10 + index,
            11 + index,
            9 + index,
            10 + index,
            1000,
        )
        for index in range(8)
    )
    dataset = MarketDataSet("data-v1", DataZone.DEVELOPMENT, bars)
    strategy = validate_strategy(
        {
            "schema_version": 1,
            "id": "pipeline-feature",
            "family": "macro",
            "generation": 0,
            "indicators": {"fast": {"type": "SMA", "period": 2}},
            "features": {"macro": {"feature_id": "macro_returns"}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "macro", "value": 0}],
            },
            "exit": {
                "logic": "AND",
                "conditions": [{"op": "less_than", "left": "macro", "value": -1}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )
    spec = FeatureSpec(
        name="macro_returns",
        family="macro",
        inputs=("MACRO.close",),
        calculator="returns",
        lookback=2,
        formula="returns(MACRO.close, 2)",
        status="REGISTERED",
    )
    observations = tuple(
        SeriesObservation(
            "MACRO",
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            100 + index,
        )
        for index in range(8)
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
        feature_specs={"macro_returns": spec},
        feature_inputs={
            "open": tuple(bar.open for bar in bars),
            "high": tuple(bar.high for bar in bars),
            "low": tuple(bar.low for bar in bars),
            "close": tuple(bar.close for bar in bars),
            "volume": tuple(bar.volume for bar in bars),
        },
        external_series=SeriesDataSet("macro-v1", DataZone.DEVELOPMENT, observations),
    )

    assert result.funnel[0].feature_ids == ("macro_returns",)


def test_generation_pipeline_uses_profitability_in_robust_score() -> None:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            "TEST",
            100 + index,
            101 + index,
            99 + index,
            100 + index,
            1000,
        )
        for index in range(20)
    )
    strategy = validate_strategy(
        {
            "schema_version": 1,
            "id": "pipeline-profitability",
            "family": "trend",
            "generation": 0,
            "indicators": {"fast": {"type": "SMA", "period": 2}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
            },
            "exit": {
                "logic": "AND",
                "conditions": [{"op": "less_than", "left": "close", "value": 0}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )

    result = GenerationPipeline().run(
        parent=strategy,
        dataset=MarketDataSet("data-v1", DataZone.DEVELOPMENT, bars),
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

    assert result.funnel[0].score > 0


def test_generation_pipeline_rejects_validation_zone_research() -> None:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            "TEST",
            100 + index,
            101 + index,
            99 + index,
            100 + index,
            1000,
        )
        for index in range(8)
    )
    strategy = validate_strategy(
        {
            "schema_version": 1,
            "id": "validation-zone-denied",
            "family": "trend",
            "generation": 0,
            "indicators": {"fast": {"type": "SMA", "period": 2}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
            },
            "exit": {
                "logic": "AND",
                "conditions": [{"op": "less_than", "left": "close", "value": 0}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )

    with pytest.raises(PermissionError, match="development"):
        GenerationPipeline().run(
            parent=strategy,
            dataset=MarketDataSet("validation", DataZone.VALIDATION, bars),
            operations=(),
            domains=(),
            method="grid",
            count=1,
            seed=0,
            funnel=FunnelConfig(require_validation=False),
        )


def test_temporal_validation_is_labeled_as_holdout_not_optimization() -> None:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            "TEST",
            100 + index,
            101 + index,
            99 + index,
            100 + index,
            1000,
        )
        for index in range(12)
    )
    strategy = validate_strategy(
        {
            "schema_version": 1,
            "id": "temporal-holdout-label",
            "family": "trend",
            "generation": 0,
            "indicators": {"fast": {"type": "SMA", "period": 2}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
            },
            "exit": {
                "logic": "AND",
                "conditions": [{"op": "less_than", "left": "close", "value": 0}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )

    result = GenerationPipeline().run(
        parent=strategy,
        dataset=MarketDataSet("development", DataZone.DEVELOPMENT, bars),
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
            require_risk_compliance=False,
            min_annual_trades=None,
        ),
    )

    assert result.funnel[0].validation_folds
    assert all(fold["method"] == "temporal_holdout" for fold in result.funnel[0].validation_folds)
    assert all(fold["selection_applied"] is False for fold in result.funnel[0].validation_folds)

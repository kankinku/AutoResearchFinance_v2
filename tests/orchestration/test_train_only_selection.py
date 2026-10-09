"""The optimizer is forbidden to select a strategy using its test window."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.data.contracts import Bar, MarketDataSet
from evaluation.selector import FunnelConfig
from mutation.parameter import ParameterDomain
from orchestration.pipeline import GenerationPipeline
from strategy_ir.schema import FeatureRef, StrategyIR


def strategy() -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "locked-selection",
            "family": "test",
            "generation": 0,
            "indicators": {"ma": {"type": "SMA", "period": 2}},
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


def data(future: tuple[float, ...] = (90, 80, 70, 60, 50, 40)) -> MarketDataSet:
    closes = (10, 11, 12, 13, 14, 15) + future
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            "AAA",
            close,
            close,
            close,
            close,
            1000,
        )
        for i, close in enumerate(closes)
    )
    return MarketDataSet("selection-data-v1", "development", bars)


def evaluate(dataset: MarketDataSet):
    return GenerationPipeline().run(
        parent=strategy(),
        dataset=dataset,
        operations=(),
        domains=(ParameterDomain("risk.position_size_pct", (50.0, 100.0)),),
        method="grid",
        count=2,
        seed=42,
        funnel=FunnelConfig(
            min_fast_trades=0,
            min_full_trades=0,
            min_fast_return=-1,
            min_full_return=-1,
            min_robust_score=0,
            require_validation=False,
        ),
    )


def test_selection_is_performed_on_training_data_before_test() -> None:
    report = evaluate(data()).train_only_selection
    assert report is not None
    assert report.status == "EVALUATED"
    assert len(report.folds) == 2
    assert report.selection_trials == 4
    assert all(fold.selection_applied for fold in report.folds)
    assert all(fold.train_end_at < fold.test_start_at for fold in report.folds)
    assert all(fold.candidate_count == 2 for fold in report.folds)
    assert report.folds[0].train_total_return > 0
    assert report.folds[0].test_total_return < 0


def test_changing_future_candles_cannot_change_earlier_selection() -> None:
    original = evaluate(data()).train_only_selection
    changed = evaluate(data((190, 180, 170, 160, 150, 140))).train_only_selection
    assert original is not None and changed is not None
    first = original.folds[0]
    other = changed.folds[0]
    assert first.selected_candidate_hash == other.selected_candidate_hash
    assert first.train_total_return == other.train_total_return
    assert first.train_dataset_hash == other.train_dataset_hash


def test_train_only_selection_fails_closed_when_features_are_supplied() -> None:
    parent = strategy()
    parent.features = {"external": FeatureRef(feature_id="market_feature")}
    result = GenerationPipeline().run(
        parent=parent,
        dataset=data(),
        operations=(),
        domains=(),
        method="grid",
        count=1,
        seed=42,
        funnel=FunnelConfig(
            min_fast_trades=0,
            min_full_trades=0,
            min_fast_return=-1,
            min_full_return=-1,
            min_robust_score=0,
            require_validation=False,
        ),
        feature_values={"external": tuple(float(i) for i in range(12))},
    )
    assert result.train_only_selection is not None
    assert result.train_only_selection.status == "UNSUPPORTED_UNVERIFIED_FEATURES"
    assert result.train_only_selection.folds == ()


def test_pipeline_deduplicates_equivalent_generated_parameter_points() -> None:
    result = GenerationPipeline().run(
        parent=strategy(),
        dataset=data(),
        operations=(),
        domains=(ParameterDomain("risk.stop_loss_pct", (1.0, 1.0)),),
        method="grid",
        count=2,
        seed=2,
        funnel=FunnelConfig(
            min_fast_trades=0,
            min_full_trades=0,
            min_fast_return=-1,
            min_full_return=-1,
            min_robust_score=0,
            require_validation=False,
        ),
    )
    assert len(result.candidates) == 1
    assert len(result.funnel) == 1
    assert result.train_only_selection is not None
    assert all(fold.candidate_count == 1 for fold in result.train_only_selection.folds)

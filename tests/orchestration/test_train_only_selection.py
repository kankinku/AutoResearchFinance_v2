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


def test_prior_research_trials_are_counted_in_statistics() -> None:
    result = GenerationPipeline().run(
        parent=strategy(),
        dataset=data(),
        operations=(),
        domains=(ParameterDomain("risk.position_size_pct", (50.0, 100.0)),),
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
        prior_trials=21,
    )
    assert result.multiple_testing_trials == 23


def test_bayesian_previous_observations_cannot_claim_train_only_provenance() -> None:
    from mutation.parameter import BayesianObservation

    result = GenerationPipeline().run(
        parent=strategy(),
        dataset=data(),
        operations=(),
        domains=(ParameterDomain("risk.position_size_pct", (50.0, 100.0)),),
        method="bayesian",
        count=2,
        seed=4,
        observations=[BayesianObservation({"risk.position_size_pct": 100.0}, score=0.99)],
        funnel=FunnelConfig(
            min_fast_trades=0,
            min_full_trades=0,
            min_fast_return=-1,
            min_full_return=-1,
            min_robust_score=0,
            require_validation=False,
        ),
    )
    report = result.train_only_selection
    assert report is not None
    assert report.status == "UNVERIFIED_UPSTREAM_OPTIMIZATION"
    assert report.folds == ()
    assert report.upstream_selection_verified is False
    assert report.sealed_oos_evaluated is False


def test_fixed_cohort_train_selection_does_not_assert_upstream_fit_is_verified() -> None:
    report = evaluate(data()).train_only_selection
    assert report is not None
    assert report.status == "EVALUATED"
    assert report.upstream_selection_verified is False


def test_each_fold_regenerates_candidates_only_after_training_cutoff(monkeypatch) -> None:
    import orchestration.pipeline as pipeline_module

    original = pipeline_module.generate_candidates
    observed_seeds: list[int] = []

    def traced_generate(*args, **kwargs):
        observed_seeds.append(kwargs["seed"])
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "generate_candidates", traced_generate)
    report = evaluate(data()).train_only_selection
    assert report is not None
    assert report.status == "EVALUATED"
    assert observed_seeds == [42, 42, 43]  # Cohort diagnostics, then each fold.
    for fold in report.folds:
        assert fold.candidate_generation_cutoff_at == fold.train_end_at
        assert fold.generation_seed == 42 + fold.fold
        assert fold.selected_candidate_hash in fold.generated_candidate_hashes
        assert len(fold.generated_candidate_hashes) == fold.candidate_count


def test_changes_after_first_fold_do_not_affect_its_generated_candidates() -> None:
    original = evaluate(data()).train_only_selection
    modified = evaluate(data((1000, 1000, 1000, 1000, 1000, 1000))).train_only_selection
    assert original is not None and modified is not None
    assert (
        original.folds[0].generated_candidate_hashes == modified.folds[0].generated_candidate_hashes
    )
    assert original.folds[0].selected_candidate_hash == modified.folds[0].selected_candidate_hash


def test_near_miss_candidates_cannot_become_next_best_strategy() -> None:
    from dataclasses import replace

    from orchestration.evaluation_runner import _best_strategy_payload

    result = evaluate(data())
    statuses = tuple(replace(item, status="NEAR_MISS") for item in result.funnel)
    assert statuses
    assert _best_strategy_payload(replace(result, funnel=statuses)) == {}


def test_only_eligible_train_selected_survivor_can_become_best_strategy() -> None:
    from dataclasses import replace

    from orchestration.evaluation_runner import _best_strategy_payload

    result = evaluate(data())
    selection = result.train_only_selection
    assert selection is not None and selection.status == "EVALUATED"
    assert len(result.funnel) >= 2
    selected_hash = selection.folds[-1].selected_candidate_hash
    statuses = tuple(
        replace(
            item,
            status="SURVIVOR" if item.candidate_hash == selected_hash else "NEAR_MISS",
            score=0.0 if item.candidate_hash == selected_hash else 1.0,
        )
        for item in result.funnel
    )
    chosen = _best_strategy_payload(replace(result, funnel=statuses))
    assert chosen["best_strategy"] == next(
        candidate.strategy.model_dump(mode="json", by_alias=True)
        for candidate in result.candidates
        if candidate.candidate_hash == selected_hash
    )


def test_next_parent_is_locked_to_latest_train_fold_not_full_period_score() -> None:
    from dataclasses import replace

    from orchestration.evaluation_runner import _best_strategy_payload

    result = evaluate(data())
    selection = result.train_only_selection
    assert selection is not None and selection.status == "EVALUATED"
    chosen_hash = selection.folds[-1].selected_candidate_hash
    assert chosen_hash in {item.candidate_hash for item in result.candidates}
    inverted = tuple(
        replace(
            item,
            status="SURVIVOR",
            score=1000.0 if item.candidate_hash != chosen_hash else 0.0,
        )
        for item in result.funnel
    )
    payload = _best_strategy_payload(replace(result, funnel=inverted))
    assert payload["best_strategy"] == next(
        item.strategy.model_dump(mode="json", by_alias=True)
        for item in result.candidates
        if item.candidate_hash == chosen_hash
    )
    assert payload["successor_selection_basis"] == "LATEST_TRAIN_ONLY_FOLD"


def test_next_parent_cannot_fallback_to_holdout_winner_when_train_pick_rejected() -> None:
    from dataclasses import replace

    from orchestration.evaluation_runner import _best_strategy_payload

    result = evaluate(data())
    selection = result.train_only_selection
    assert selection is not None and selection.status == "EVALUATED"
    chosen_hash = selection.folds[-1].selected_candidate_hash
    manipulated = tuple(
        replace(
            item,
            status="REJECT" if item.candidate_hash == chosen_hash else "SURVIVOR",
            score=0.0 if item.candidate_hash == chosen_hash else 1000.0,
        )
        for item in result.funnel
    )
    assert any(item.status == "SURVIVOR" for item in manipulated)
    assert _best_strategy_payload(replace(result, funnel=manipulated)) == {}


def test_later_test_prices_cannot_change_train_only_successor() -> None:
    from dataclasses import replace

    from orchestration.evaluation_runner import _best_strategy_payload

    first = evaluate(data())
    # Indices 9-11 are after the *last* fold's training cutoff index 8.
    changed = evaluate(data((90, 80, 70, 999, 998, 997)))
    assert first.train_only_selection is not None
    assert changed.train_only_selection is not None
    assert (
        first.train_only_selection.folds[-1].train_dataset_hash
        == changed.train_only_selection.folds[-1].train_dataset_hash
    )
    def all_eligible(value):
        return replace(
            value,
            funnel=tuple(replace(item, status="SURVIVOR") for item in value.funnel),
        )
    assert (
        _best_strategy_payload(all_eligible(first))["best_strategy"]
        == _best_strategy_payload(all_eligible(changed))["best_strategy"]
    )


def test_unverified_fold_selection_cannot_choose_next_parent() -> None:
    from dataclasses import replace

    from orchestration.evaluation_runner import _best_strategy_payload
    from orchestration.train_only import TrainOnlySelectionReport

    result = evaluate(data())
    all_eligible = tuple(replace(item, status="SURVIVOR") for item in result.funnel)
    unsafe = replace(
        result,
        funnel=all_eligible,
        train_only_selection=TrainOnlySelectionReport(
            "UNVERIFIED_UPSTREAM_OPTIMIZATION",
            reason="unverified Bayesian score provenance",
        ),
    )
    assert _best_strategy_payload(unsafe) == {}

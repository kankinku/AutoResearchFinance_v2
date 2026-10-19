"""P0-2: real StrategyIR feature mutation and canonical costed backtest boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from application.catalog_service import FeatureCatalogService
from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, DataZone, MarketDataSet, SeriesDataSet, SeriesObservation
from core.features.contracts import FeatureSpec
from core.features.registry import research_feature_specs
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import IntentEligibilityError, apply_intent, intent_to_operations
from strategy_ir.schema import StrategyIR


def _parent() -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "intent_p0",
            "family": "development_feature",
            "generation": 0,
            "indicators": {"baseline": {"type": "SMA", "period": 2}},
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"op": "greater_than", "left": "close", "value": 0},
                ],
            },
            "exit": {
                "logic": "AND",
                "conditions": [
                    {"op": "less_equal", "left": "close", "value": 0},
                ],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )


def _market() -> MarketDataSet:
    t0 = datetime(2024, 1, 1, 21, tzinfo=timezone.utc)
    close = tuple(100.0 + index * 0.02 + (index % 19) * 0.3 for index in range(120))
    bars = tuple(
        Bar(t0 + timedelta(days=i), "QQQ", c, c + 1, c - 1, c, 10000) for i, c in enumerate(close)
    )
    return MarketDataSet("p0_intent_synthetic", DataZone.DEVELOPMENT, bars)


def _intent(*, identifier: str, alias: str, inputs: tuple[str, ...] = ()) -> ResearchIntent:
    return ResearchIntent(
        mode="structure",
        parent_ids=("intent_p0",),
        rationale="compare a verified indicator feature against a fixed close threshold",
        feature_selections=({"alias": alias, "feature_id": identifier, "inputs": inputs},),
        operations=(
            {
                "op": "REPLACE_RULE",
                "path": "entry.conditions.0",
                "condition": {
                    "op": "greater_than",
                    "left": alias,
                    "value": 0.5,
                },
            },
        ),
    )


def _run(strategy: StrategyIR, *, series: SeriesDataSet | None = None):
    market = _market()
    bars = market.bars
    inputs = {
        key: tuple(float(getattr(bar, key)) for bar in bars)
        for key in ("open", "high", "low", "close", "volume")
    }
    specs = {spec.name: spec for spec in research_feature_specs()}
    return BacktestEngine().run(
        BacktestRequest(
            run_id="p0-intent-run",
            strategy_hash="unhashed",
            dataset=market,
            initial_cash=10000.0,
            strategy=strategy,
            feature_specs=specs,
            feature_inputs=inputs,
            external_series=series,
        )
    )


def test_native_scalar_feature_selection_reaches_real_backtest() -> None:
    parent = _parent()
    intent = _intent(identifier="sma", alias="regime_sma")
    child = apply_intent(parent, intent, research_feature_specs())
    assert child.features["regime_sma"].feature_id == "sma"
    assert child.entry.conditions[0].left == "regime_sma"
    result = _run(child)
    assert result.exit_status == "SUCCEEDED"
    assert len(result.trades) > 0
    assert child.generation == parent.generation + 1
    assert not any(x.side == "sell" for x in result.trades)  # no exit policy in this fixture


def test_external_asof_feature_reaches_real_backtest_without_future_values() -> None:
    parent = _parent()
    intent = _intent(identifier="vix_percentile", alias="vix_context", inputs=("VIX.close",))
    child = apply_intent(parent, intent, research_feature_specs())
    market = _market()
    # Last observation is late: cannot be used on the last completed market bar.
    t = market.bars[-1].timestamp
    series = SeriesDataSet(
        "p0-vix-fixture",
        DataZone.DEVELOPMENT,
        (
            SeriesObservation("VIX", market.bars[0].timestamp, 10),
            SeriesObservation("VIX", market.bars[60].timestamp, 12),
            SeriesObservation("VIX", t, 60, available_at=t + timedelta(days=2)),
        ),
    )
    result = _run(child, series=series)
    assert result.exit_status == "SUCCEEDED"
    # The delayed VIX revision arrives AFTER the market's final completed
    # bar. Changing it cannot alter any historical trading decision.
    alternative = SeriesDataSet(
        "p0-vix-fixture",
        DataZone.DEVELOPMENT,
        (
            series.observations[0],
            series.observations[1],
            SeriesObservation("VIX", t, 6000, available_at=t + timedelta(days=2)),
        ),
    )
    replay = _run(child, series=alternative)
    assert replay.equity_curve_hash == result.equity_curve_hash
    assert replay.trades == result.trades


@pytest.mark.parametrize("name", ["volume_profile", "order_flow_delta", "session_flag"])
def test_specialized_catalog_feature_rejected_before_candidate_evaluation(name: str) -> None:
    with pytest.raises(IntentEligibilityError, match="INTENT_FEATURE_NOT_EXECUTABLE"):
        intent_to_operations(
            _intent(identifier=name, alias="specialized"), research_feature_specs()
        )


def test_restricted_source_rejected_before_candidate_evaluation() -> None:
    restricted = FeatureSpec(
        name="restricted_source",
        family="custom",
        inputs=("close",),
        calculator="sma",
        lookback=14,
        formula="sma(close,14)",
        status="REGISTERED",
        source_licenses=("CC BY-NC-SA 4.0",),
    )
    with pytest.raises(IntentEligibilityError, match="INTENT_FEATURE_LICENSE_REVIEW"):
        intent_to_operations(
            _intent(identifier="restricted_source", alias="restricted"),
            (restricted,),
        )


def test_legacy_catalog_distinguishes_registration_from_execution_readiness() -> None:
    service = FeatureCatalogService()
    values = service.research_features()
    assert len(values) == 173
    assert set(values[0]) == {"name", "family", "inputs", "calculator", "lookback", "timeframe"}
    summary = service.capability_summary()
    assert summary["registered_count"] == 173
    assert 0 < summary["observed_scalar_calculation_count"] < 173
    assert "volume_profile" in summary["not_bar_aligned"]
    assert "rsi.wilder" in summary["no_observable_output_on_probe"]


def test_typed_add_feature_operation_honors_same_specialized_block() -> None:
    intent = ResearchIntent(
        mode="structure",
        parent_ids=("intent_p0",),
        rationale="specialized observations are not an OHLCV bar series",
        operations=(
            {
                "op": "ADD_FEATURE",
                "path": "features.bad_profile",
                "feature": {"feature_id": "volume_profile"},
            },
        ),
    )
    with pytest.raises(IntentEligibilityError, match="INTENT_FEATURE_NOT_EXECUTABLE"):
        intent_to_operations(intent, research_feature_specs())


def test_llm_research_context_explains_capability_gaps(tmp_path) -> None:
    from application.research_service import ResearchService

    context = ResearchService(tmp_path / "state").context()
    summary = context["feature_capability_summary"]
    assert summary["registered_count"] == len(context["feature_catalog"]) == 173
    assert "volume_profile" in summary["not_bar_aligned"]
    assert "Registered is not proof" in summary["usage_policy"]
    assert "sealed_oos" not in context

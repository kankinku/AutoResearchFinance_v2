"""P0: advertised capability is not the same as executable research capability."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.data.contracts import Bar, DataZone, MarketDataSet
from core.features.contracts import FeatureSpec
from core.features.registry import research_feature_specs
from research.indicator_engine.capability_audit import (
    audit_academic_capabilities,
    audit_native_capabilities,
)
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices


def _market() -> MarketDataSet:
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(650):
        price = 100.0 + i * 0.07 + (i % 13) * 0.12
        bars.append(
            Bar(t0 + timedelta(days=i), "QQQ", price, price + 1.2, price - 1.2, price, 100_000.0)
        )
    return MarketDataSet("capability-p0-synthetic", DataZone.DEVELOPMENT, tuple(bars))


def _catalog(tmp_path: Path) -> ResearchCatalog:
    catalog = ResearchCatalog(tmp_path / "academic-capabilities.sqlite")
    seed_approved_references(catalog)
    for signal_id in ("time_series_momentum", "previous_range_breakout", "sma_direction"):
        candidate = catalog.get_indicator(signal_id)
        catalog.verify_and_register(signal_id, verify_signal_on_synthetic_prices(candidate))
    return catalog


def test_native_catalog_does_not_claim_llm_execution_based_on_registered_flag() -> None:
    records = audit_native_capabilities()
    declared = research_feature_specs()
    assert len(records) == len(declared)
    assert all(r["surface"] == "native_feature_catalog" for r in records)
    assert all(not r["llm_exposed"] for r in records)
    assert all(r["status"] != "SUPPORTED_AND_EXECUTABLE" for r in records)
    assert {r["name"] for r in records} == {s.name for s in declared}


def test_native_catches_unwired_specialized_and_external_capabilities() -> None:
    records = {r["name"]: r for r in audit_native_capabilities()}
    assert records["volume_profile"]["status"] == "PARTIAL"
    assert records["volume_profile"]["reason"] == "SPECIALIZED_NOT_BAR_ALIGNED"
    assert records["vix_percentile"]["reason"] == "EXTERNAL_OBSERVATIONS_REQUIRED"
    assert records["sma"]["reason"] == "NOT_IN_ACADEMIC_PLAN_PROVIDER"


def test_audit_fails_closed_for_unsupported_and_restricted_features() -> None:
    missing = FeatureSpec(
        name="missing_calc",
        family="test",
        inputs=("close",),
        calculator="never_supported",
        lookback=2,
        formula="never_supported(close)",
        status="REGISTERED",
    )
    restricted = missing.model_copy(
        update={"name": "restricted", "source_licenses": ("CC BY-NC-SA 4.0",)}
    )
    records = {r["name"]: r for r in audit_native_capabilities((missing, restricted))}
    assert records["missing_calc"]["status"] == "MISSING"
    assert records["restricted"]["status"] == "BLOCKED_LICENSE"


def test_academic_provider_only_exposes_verified_runnable_indicators(tmp_path: Path) -> None:
    rows = audit_academic_capabilities(_catalog(tmp_path), _market())
    lookup = {r["name"]: r for r in rows}
    assert lookup["time_series_momentum"]["status"] == "SUPPORTED_AND_EXECUTABLE"
    assert lookup["previous_range_breakout"]["llm_exposed"]
    assert lookup["sma_direction"]["llm_exposed"]
    assert lookup["parkinson_variance"]["status"] == "PARTIAL"
    assert not lookup["parkinson_variance"]["llm_exposed"]
    assert lookup["cross_sectional_momentum"]["status"] == "PARTIAL"
    assert not lookup["cross_sectional_momentum"]["llm_exposed"]
    assert all(r["llm_exposed"] == (r["status"] == "SUPPORTED_AND_EXECUTABLE") for r in rows)


def test_three_distinct_llm_plans_compile_replay_and_costed_evaluate(tmp_path: Path) -> None:
    """P0 baseline: current approved provider path supports three distinct shapes."""
    from research.indicator_engine.algorithm_plan import (
        AlgorithmPlan,
        compile_provider_algorithm_plan,
        evaluate_algorithm_plan,
    )

    catalog = _catalog(tmp_path)
    market = _market()
    plans = (
        {
            "plan_id": "simple_regime_01",
            "cases": [
                {
                    "case_id": "uptrend",
                    "when": {
                        "indicator_id": "sma_direction",
                        "op": "greater_than",
                        "threshold": 0.5,
                    },
                    "votes": [{"indicator_id": "time_series_momentum", "weight": 1}],
                    "min_score": 0.5,
                }
            ],
            "unmatched": "FLAT",
            "position_size_pct": 100,
        },
        {
            "plan_id": "weighted_regime_01",
            "cases": [
                {
                    "case_id": "uptrend",
                    "when": {
                        "indicator_id": "sma_direction",
                        "op": "greater_than",
                        "threshold": 0.5,
                    },
                    "votes": [
                        {"indicator_id": "time_series_momentum", "weight": 0.7},
                        {"indicator_id": "previous_range_breakout", "weight": 0.3},
                    ],
                    "min_score": 0.6,
                }
            ],
            "unmatched": "FLAT",
            "position_size_pct": 100,
        },
        {
            "plan_id": "two_regimes_01",
            "cases": [
                {
                    "case_id": "uptrend",
                    "when": {
                        "indicator_id": "sma_direction",
                        "op": "greater_than",
                        "threshold": 0.5,
                    },
                    "votes": [{"indicator_id": "time_series_momentum", "weight": 1}],
                    "min_score": 0.5,
                },
                {
                    "case_id": "downtrend",
                    "when": {"indicator_id": "sma_direction", "op": "less_equal", "threshold": 0.5},
                    "votes": [{"indicator_id": "previous_range_breakout", "weight": 1}],
                    "min_score": 0.5,
                },
            ],
            "unmatched": "FLAT",
            "position_size_pct": 100,
        },
    )
    plan_hashes = []
    for payload in plans:

        class Provider:
            def __init__(self, submitted):
                self.submitted = submitted

            def propose(self, context):
                assert {x["indicator_id"] for x in context["verified_indicators"]} == {
                    "time_series_momentum",
                    "previous_range_breakout",
                    "sma_direction",
                }
                return self.submitted

        compiled = compile_provider_algorithm_plan(catalog, Provider(payload), market)
        assert compiled.plan == AlgorithmPlan.model_validate(payload)
        result = evaluate_algorithm_plan(catalog, compiled, market)
        assert result.status == "NON_PIT_DEVELOPMENT_RESULT"
        assert not result.broker_executable
        assert result.replay_hash == compiled.compiled.replay.replay_hash
        assert len(compiled.compiled.feature_values["plan_entry"]) == len(market.bars)
        plan_hashes.append(compiled.plan_hash)
    assert len(set(plan_hashes)) == 3


def test_existing_typed_plan_baseline_hashes_remain_identical(tmp_path: Path) -> None:
    """Preserve one historical pre-change StrategyIR/replay/equity fingerprint."""
    from research.indicator_engine.algorithm_plan import (
        AlgorithmPlan,
        compile_algorithm_plan,
        evaluate_algorithm_plan,
    )
    from research.indicator_engine.signals import verify_signal_on_synthetic_prices

    catalog = _catalog(tmp_path)
    prior = catalog.get_indicator("parkinson_variance")
    catalog.verify_and_register(prior.signal_id, verify_signal_on_synthetic_prices(prior))
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(650):
        price = 100.0 + i * 0.09 + (i % 22) * 0.06
        if i >= 440:
            price = 160.0 - (i - 440) * 0.13 + (i % 22) * 0.3
        span = 0.2 if i < 400 else 2.2
        bars.append(
            Bar(t0 + timedelta(days=i), "QQQ", price, price + span, price - span, price, 100_000.0)
        )
    market = MarketDataSet("algo_synthetic", DataZone.DEVELOPMENT, tuple(bars))
    plan = AlgorithmPlan.model_validate(
        {
            "plan_id": "research_switch_01",
            "cases": [
                {
                    "case_id": "calm",
                    "when": {
                        "indicator_id": "parkinson_variance",
                        "op": "less_equal",
                        "threshold": 0.0001,
                    },
                    "votes": [
                        {"indicator_id": "time_series_momentum", "weight": 0.7},
                        {"indicator_id": "previous_range_breakout", "weight": 0.3},
                    ],
                    "min_score": 0.5,
                },
                {
                    "case_id": "volatile",
                    "when": {
                        "indicator_id": "parkinson_variance",
                        "op": "greater_than",
                        "threshold": 0.0001,
                    },
                    "votes": [
                        {"indicator_id": "previous_range_breakout", "weight": 0.8},
                        {"indicator_id": "time_series_momentum", "weight": 0.2},
                    ],
                    "min_score": 0.5,
                },
            ],
            "unmatched": "FLAT",
            "position_size_pct": 100,
        }
    )
    compiled = compile_algorithm_plan(catalog, plan, market)
    evaluated = evaluate_algorithm_plan(catalog, compiled, market)
    assert compiled.plan_hash == "da5fcf076a27a07dc2e616d6aa83aa8a4720109f98d10dc6c53be38454729ec0"
    assert (
        evaluated.strategy_hash
        == "34d07083981652a46d15449338647698fa4a93c53df6cd0c48decc7e83671204"
    )
    assert (
        evaluated.replay_hash == "1e79ec6a8b4e4880f6db2c056ce0976e57e8d8ed9ca80b94c050327933401bd3"
    )
    assert (
        evaluated.equity_hash == "e89d510c7be83b9cc5653e5bca8f5845ef8e0d568ebf30730e8c68dc4d3d42bf"
    )
    assert evaluated.trades_count == 4

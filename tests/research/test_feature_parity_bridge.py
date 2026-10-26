"""Feature bridge must not confuse standard deviation and variance or trade."""

from __future__ import annotations

import pytest

from research.indicator_engine.feature_parity_bridge import verify_feature_signal_parity
from research.indicator_engine.models import CANONICAL_FORMULAS, IndicatorCandidate
from research.indicator_engine.seed import ACADEMIC_PAPERS, ACADEMIC_SIGNALS


def _prices() -> dict[str, tuple[float, ...]]:
    close = tuple(100.0 + i * 0.04 + (i % 17) * 0.13 for i in range(630))
    return {
        "open": tuple(x + (0.08 if i % 2 else -0.05) for i, x in enumerate(close)),
        "high": tuple(x + 1.0 for x in close),
        "low": tuple(x - 1.0 for x in close),
        "close": close,
    }


@pytest.mark.parametrize(
    "signal",
    [
        "sma_direction",
        "ema_direction",
        "parkinson_variance",
        "garman_klass_variance",
    ],
)
def test_legacy_generic_formula_parity_is_dimensionally_correct(signal):
    if signal == "ema_direction":
        # Synthetic fixture; no assertion that this signal is verified in production.
        candidate = IndicatorCandidate.model_validate(
            {
                "signal_id": "ema_direction",
                "paper_doi": ACADEMIC_PAPERS[0].doi,
                "calculator": "ema_direction",
                "family": "trend",
                "role": "entry",
                "required_fields": ["close"],
                "lookback": 20,
                "formula": CANONICAL_FORMULAS["ema_direction"],
                "scope": "single_asset",
                "status": "VERIFIED",
            }
        )
    else:
        candidate = next(x for x in ACADEMIC_SIGNALS if x.signal_id == signal)
        candidate = candidate.model_copy(update={"status": "VERIFIED"})
    result = verify_feature_signal_parity(candidate, _prices())
    assert result["sample_count"] >= 20
    assert result["eligible_for_automatic_academic_promotion"] is False
    if signal.endswith("variance"):
        assert result["conversion"] == "square_standard_deviation"
        assert result["academic_output_unit"] == "variance"


def test_unknown_and_unverified_signals_do_not_get_promoted():
    candidate = ACADEMIC_SIGNALS[0]
    with pytest.raises(ValueError, match="VERIFIED"):
        verify_feature_signal_parity(candidate, _prices())
    wrong = candidate.model_copy(
        update={"status": "VERIFIED", "calculator": "time_series_momentum"}
    )
    with pytest.raises(ValueError, match="no reviewed"):
        verify_feature_signal_parity(wrong, _prices())


def test_missing_prices_and_changed_schema_rejected():
    candidate = ACADEMIC_SIGNALS[0].model_copy(update={"status": "VERIFIED"})
    prices = _prices()
    del prices["close"]
    with pytest.raises(ValueError, match="input schema"):
        verify_feature_signal_parity(candidate, prices)
    candidate = candidate.model_copy(update={"execution_delay_bars": 0})
    with pytest.raises(ValueError, match="next-bar"):
        verify_feature_signal_parity(candidate, _prices())


def test_parity_signals_run_through_existing_typed_s2_without_promotion(tmp_path):
    """The legacy vetted academic compiler stays the authority, not generic features."""
    from datetime import datetime, timedelta, timezone

    from core.data.contracts import Bar, DataZone, MarketDataSet
    from research.indicator_engine.algorithm_plan import (
        AlgorithmPlan,
        compile_algorithm_plan,
        evaluate_algorithm_plan,
    )
    from research.indicator_engine.catalog import ResearchCatalog
    from research.indicator_engine.seed import seed_approved_references
    from research.indicator_engine.signals import verify_signal_on_synthetic_prices

    catalog = ResearchCatalog(tmp_path / "reviewed_only.sqlite")
    seed_approved_references(catalog)
    for name in ("sma_direction", "parkinson_variance", "time_series_momentum"):
        sig = catalog.get_indicator(name)
        catalog.verify_and_register(name, verify_signal_on_synthetic_prices(sig))
        if name in ("sma_direction", "parkinson_variance"):
            parity = verify_feature_signal_parity(catalog.get_indicator(name), _prices())
            assert parity["eligible_for_automatic_academic_promotion"] is False

    prices = _prices()
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    market = MarketDataSet(
        "fixture_parity_development",
        DataZone.DEVELOPMENT,
        tuple(
            Bar(
                t0 + timedelta(days=i),
                "QQQ",
                prices["open"][i],
                prices["high"][i],
                prices["low"][i],
                prices["close"][i],
                100000.0,
            )
            for i in range(len(prices["close"]))
        ),
    )
    plan = AlgorithmPlan.model_validate(
        {
            "plan_id": "parity_typed_s2_01",
            "cases": [
                {
                    "case_id": "low_risk",
                    "when": {
                        "indicator_id": "parkinson_variance",
                        "op": "less_equal",
                        "threshold": 0.05,
                    },
                    "votes": [{"indicator_id": "time_series_momentum", "weight": 1.0}],
                    "min_score": 0.5,
                }
            ],
            "unmatched": "FLAT",
            "position_size_pct": 100,
        }
    )
    compiled = compile_algorithm_plan(catalog, plan, market)
    assert compiled.broker_executable is False
    report = evaluate_algorithm_plan(catalog, compiled, market)
    assert report.trades_count >= 0
    assert compiled.compiled.strategy.entry.conditions[0].left == "plan_entry"

"""Risk overlay uses close-confirmed fractions for next-open, cash-only execution."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.risk_replay import (
    RiskReplayPolicy,
    evaluate_academic_risk_overlay,
)
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices


def _fixture(tmp_path: Path, risk: str = "volatility_managed_exposure", *, n: int = 320):
    catalog = ResearchCatalog(tmp_path / "research.sqlite")
    seed_approved_references(catalog)
    names = ("time_series_momentum", "sma_direction", risk)
    for name in names:
        indicator = catalog.get_indicator(name)
        catalog.verify_and_register(
            name, verify_signal_on_synthetic_prices(indicator)
        )
    hypothesis = next(
        h for h in compose_hypotheses(catalog, signal_ids=names) if len(h.signal_ids) == 3
    )
    start = datetime(2021, 1, 1, 21, tzinfo=timezone.utc)
    bars = []
    for i in range(n):
        close = 100 + i * 0.23 + (i % 7) * 0.11 if i < n - 40 else 190 - (i - (n - 40)) * 0.6
        bars.append(
            Bar(
                timestamp=start + timedelta(days=i),
                symbol="QQQ", open=close, high=close+1.2, low=close-1.2,
                close=close, volume=1000,
            )
        )
    dataset = MarketDataSet("unverified-fixture", DataZone.DEVELOPMENT, tuple(bars))
    return catalog, hypothesis, dataset


@pytest.mark.parametrize("risk", [
    "volatility_managed_exposure",
    "parkinson_variance",
    "garman_klass_variance",
])
def test_risk_variants_replay_correctly_with_no_leverage(tmp_path: Path, risk: str) -> None:
    catalog, hypothesis, data = _fixture(tmp_path, risk)
    policy = RiskReplayPolicy(
        target_daily_variance=0.0001, max_exposure=0.7,
        rebalance_band=0.03,
    )
    first = evaluate_academic_risk_overlay(catalog, hypothesis, data, policy=policy)
    second = evaluate_academic_risk_overlay(catalog, hypothesis, data, policy=policy)
    assert first == second
    assert first.status == "NON_PIT_DEVELOPMENT_ONLY"
    assert first.broker_executable is False
    assert first.candidate_promotable is False
    assert first.out_of_sample_approved is False
    assert first.benchmark_verified is False
    assert len(first.equity_curve) == len(data.bars)
    assert len(first.fractions_at_close) == len(data.bars)
    assert all(0 <= f <= policy.max_exposure for f in first.target_fractions_at_open)
    # Market movement after the opening rebalance can change marked exposure.
    assert all(0 <= f <= 1 for f in first.fractions_at_close)
    assert first.trades_count > 0
    assert first.total_paid_costs > 0
    assert first.final_equity > 0
    for trade in first.trades:
        index = next(
            i for i, bar in enumerate(data.bars)
            if trade.timestamp == bar.timestamp.isoformat()
        )
        assert index >= 1
        assert trade.price == pytest.approx(data.bars[index].open)
    assert first == evaluate_academic_risk_overlay(catalog, hypothesis, data, policy=policy)


def test_future_close_perturbation_cannot_change_prior_decisions(tmp_path: Path) -> None:
    catalog, hypothesis, data = _fixture(tmp_path)
    policy = RiskReplayPolicy(max_exposure=0.6)
    baseline = evaluate_academic_risk_overlay(catalog, hypothesis, data, policy=policy)
    bars = list(data.bars)
    final = bars[-1]
    bars[-1] = replace(final, close=final.close+15, high=final.high+20)
    changed = MarketDataSet(data.version, data.zone, tuple(bars))
    after = evaluate_academic_risk_overlay(catalog, hypothesis, changed, policy=policy)
    assert baseline.equity_curve[:-1] == after.equity_curve[:-1]
    assert baseline.fractions_at_close[:-1] == after.fractions_at_close[:-1]
    assert baseline.trades == after.trades
    assert baseline.replay_hash != after.replay_hash


def test_short_history_warms_up_without_accidental_trades(tmp_path: Path) -> None:
    catalog, hypothesis, data = _fixture(tmp_path, n=25)
    report = evaluate_academic_risk_overlay(catalog, hypothesis, data)
    assert report.trades == ()
    assert report.final_equity == pytest.approx(10000)
    assert all(x == 0 for x in report.fractions_at_close)


def test_rejects_invalid_policy_and_sealed_data(tmp_path: Path) -> None:
    for kw in (
        {"target_daily_variance": -0.1},
        {"target_daily_variance": float("nan")},
        {"max_exposure": 1.5},
        {"max_exposure": 0.0},
        {"rebalance_band": 1.5},
    ):
        with pytest.raises(ValueError):
            RiskReplayPolicy(**kw)
    catalog, hypothesis, data = _fixture(tmp_path)
    with pytest.raises(ResearchCatalogError, match="non-development"):
        evaluate_academic_risk_overlay(
            catalog, hypothesis, MarketDataSet(data.version, DataZone.SEALED_OOS, data.bars)
        )
    with pytest.raises(ResearchCatalogError, match="forged"):
        evaluate_academic_risk_overlay(
            catalog, hypothesis.model_copy(update={"identity_hash": "0" * 64}), data,
        )


def test_development_variance_cannot_be_mistaken_for_full_exposure(tmp_path: Path) -> None:
    catalog, hypothesis, data = _fixture(tmp_path, "garman_klass_variance")
    low = evaluate_academic_risk_overlay(
        catalog, hypothesis, data, policy=RiskReplayPolicy(target_daily_variance=1e-7)
    )
    high = evaluate_academic_risk_overlay(
        catalog, hypothesis, data, policy=RiskReplayPolicy(target_daily_variance=0.001)
    )
    # The same raw variance is mapped to different risk budgets. It is not a
    # Boolean signal or a position target by itself.
    assert low.model_hash != high.model_hash
    assert low.fractions_at_close != high.fractions_at_close


def test_prefiltered_exposure_rejects_conflicting_risk_target(tmp_path: Path) -> None:
    catalog, hypothesis, data = _fixture(tmp_path, "volatility_managed_exposure")
    # For this signal the target has ALREADY been applied by the calculator.
    # Changing the policy target alone cannot silently do nothing.
    with pytest.raises(ResearchCatalogError, match="already fixed"):
        evaluate_academic_risk_overlay(
            catalog,
            hypothesis,
            data,
            policy=RiskReplayPolicy(target_daily_variance=0.0002),
        )

"""Research-only dynamic risk contract and independent cost/ledger acceptance."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.risk_adapter import (
    compile_academic_risk_plan,
    evaluate_compiled_risk_development,
    verify_risk_accounting,
)
from research.indicator_engine.risk_replay import RiskReplayPolicy
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.indicator_engine.strategy_adapter import (
    compile_research_hypothesis,
    evaluate_compiled_development,
)


def _case(tmp_path: Path, kind: str = "parkinson_variance"):
    db = ResearchCatalog(tmp_path / "papers.sqlite")
    seed_approved_references(db)
    signals = ("time_series_momentum", "sma_direction", kind)
    for signal in signals:
        item = db.get_indicator(signal)
        db.verify_and_register(signal, verify_signal_on_synthetic_prices(item))
    hypothesis = next(
        h for h in compose_hypotheses(db, signal_ids=signals) if len(h.roles) == 3
    )
    t0 = datetime(2021, 1, 1, 21, tzinfo=timezone.utc)
    bars = []
    for i in range(340):
        close = 100 + 0.25*i if i < 295 else 173.75 - 0.8*(i - 295)
        bars.append(Bar(t0 + timedelta(days=i), "QQQ", close, close + 0.5,
                        close - 0.5, close, 1000))
    return db, hypothesis, MarketDataSet("academic-fixture", DataZone.DEVELOPMENT, tuple(bars))


@pytest.mark.parametrize("kind", [
    "garman_klass_variance", "parkinson_variance", "volatility_managed_exposure"
])
def test_sidecar_compiles_and_audits_all_three_risk_models(tmp_path: Path, kind: str):
    db, hypothesis, data = _case(tmp_path, kind)
    policy = RiskReplayPolicy(max_exposure=0.7, rebalance_band=0.03)
    compiled = compile_academic_risk_plan(db, hypothesis, data, policy=policy)
    assert compiled.status == "RESEARCH_RISK_ONLY"
    assert not compiled.broker_executable and not compiled.candidate_promotable
    assert not compiled.sealed_oos_approved
    assert compiled.base.strategy.risk.position_size_pct == 100
    assert len(compiled.base.strategy.features) == 2
    assert compiled.risk_signal_id == kind
    assert compiled.plan_hash
    result = evaluate_compiled_risk_development(db, compiled, data)
    assert result.status == "NON_PIT_DEVELOPMENT_ONLY"
    assert result.trades_count > 0
    audit = verify_risk_accounting(result, data, policy=policy)
    assert audit.verified_trades == result.trades_count
    assert audit.verified_bars == len(data.bars)
    assert audit.max_equity_error < 1e-6
    assert audit.max_exposure_error < 1e-9


def test_rejects_forged_policy_plan_strategy_and_data(tmp_path: Path):
    db, hypothesis, data = _case(tmp_path)
    compiled = compile_academic_risk_plan(db, hypothesis, data)
    variants = (
        replace(compiled, plan_hash="0" * 64),
        replace(compiled, policy=RiskReplayPolicy(max_exposure=0.5)),
        replace(compiled, base=replace(
            compiled.base, strategy=compiled.base.strategy.model_copy(update={"family":"fake"})
        )),
        replace(compiled, risk_signal_id="garman_klass_variance"),
    )
    for forged in variants:
        with pytest.raises(ResearchCatalogError):
            evaluate_compiled_risk_development(db, forged, data)
    bars = list(data.bars)
    bars[-1] = replace(bars[-1], close=bars[-1].close+1, high=bars[-1].high+1)
    with pytest.raises(ResearchCatalogError):
        evaluate_compiled_risk_development(
            db, compiled, MarketDataSet(data.version, data.zone, tuple(bars))
        )
    with pytest.raises(ResearchCatalogError):
        compile_academic_risk_plan(
            db, hypothesis, MarketDataSet(data.version, DataZone.SEALED_OOS, data.bars)
        )


def test_embedded_variance_target_cannot_disagree(tmp_path: Path):
    db, hypothesis, data = _case(tmp_path, "volatility_managed_exposure")
    with pytest.raises(ResearchCatalogError, match="already fixed"):
        compile_academic_risk_plan(
            db, hypothesis, data, policy=RiskReplayPolicy(target_daily_variance=0.0002)
        )


def test_accounting_auditor_rejects_tampered_trade_cost_curve_and_target(tmp_path: Path):
    db, hypothesis, data = _case(tmp_path)
    plan = compile_academic_risk_plan(db, hypothesis, data)
    result = evaluate_compiled_risk_development(db, plan, data)
    assert result.trades
    wrong_cost = replace(result.trades[0], cost=result.trades[0].cost + 1.0)
    for forged in (
        replace(result, trades=(wrong_cost, *result.trades[1:])),
        replace(result, equity_curve=(result.equity_curve[0]+1.0, *result.equity_curve[1:])),
        replace(result, target_fractions_at_open=(1.0, *result.target_fractions_at_open[1:])),
    ):
        with pytest.raises(ResearchCatalogError, match="audit"):
            verify_risk_accounting(forged, data, policy=plan.policy)


def test_constant_full_exposure_trade_schedule_matches_canonical_engine(tmp_path: Path):
    db, hypothesis, data = _case(tmp_path)
    baseline = compose_hypotheses(db, signal_ids=hypothesis.signal_ids[:2])[0]
    native = evaluate_compiled_development(
        compile_research_hypothesis(db, baseline, data), data
    )
    # Variance in this low-volatility synthetic path keeps exposure at 100%; a
    # wide deadband avoids non-entry rebalancing. Position sizing cost conventions
    # may still differ slightly, so compare trades and tolerance, not exact P&L.
    policy = RiskReplayPolicy(target_daily_variance=0.05, max_exposure=1,
                              rebalance_band=0.25)
    plan = compile_academic_risk_plan(db, hypothesis, data, policy=policy)
    sidecar = evaluate_compiled_risk_development(db, plan, data)
    assert [(t.timestamp, t.side) for t in sidecar.trades] == [
        (t.timestamp, t.side) for t in native.trades
    ]
    assert sidecar.final_equity == pytest.approx(native.final_equity, rel=1e-4)
    audit = verify_risk_accounting(sidecar, data, policy=policy)
    assert audit.verified_trades == len(sidecar.trades)

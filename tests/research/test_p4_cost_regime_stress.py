"""P4-4 canonical development stress and lagged regime tests."""
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from core.data.contracts import DataZone
from research.indicator_engine.algorithm_plan import audit_algorithm_plan, compile_algorithm_plan
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.p4_cost_regime_stress import (
    _lagged_regime,
    evaluate_p4_cost_regime_stress,
)
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


def fixture(tmp_path: Path):
    catalog, market = _catalog(tmp_path), _market()
    plan = compile_algorithm_plan(catalog, _plan(), market)
    audit = audit_algorithm_plan(catalog, plan, market)
    evidence = {
        "evidence_hash": "a" * 64,
        "dataset_hash": market.dataset_hash,
        "strategy_hash": plan.compiled.strategy_hash,
        "audit_hash": audit.trace_hash,
        "measured_final_equity": audit.evaluation.final_equity,
        "metrics": {"trade_count": len(audit.round_trips)},
        "broker_executable": False,
        "independent_oos_approved": False,
    }
    return plan.compiled, audit, evidence, market


def test_cost_doubling_is_measured_and_baseline_replays(tmp_path: Path):
    compiled, audit, evidence, market = fixture(tmp_path)
    report = evaluate_p4_cost_regime_stress(
        compiled, audit, evidence, market, last_development_date=date(2025, 12, 31),
    )
    assert report.baseline_equity_hash == audit.evaluation.equity_hash
    assert report.audit_hash == audit.trace_hash
    assert report.dataset_hash == market.dataset_hash
    assert [s.name for s in report.scenarios] == [
        "CANONICAL", "SLIPPAGE_2X", "ALL_TRANSACTION_COSTS_2X",
    ]
    base, slip, allcost = report.scenarios
    assert base.total_paid_costs == pytest.approx(audit.evaluation.total_paid_costs)
    assert base.total_return == pytest.approx(
        audit.evaluation.final_equity / audit.evaluation.initial_cash - 1
    )
    assert slip.total_paid_costs > base.total_paid_costs
    assert allcost.total_paid_costs > base.total_paid_costs
    assert slip.total_return < base.total_return
    assert allcost.total_return < base.total_return
    assert report.independent_oos_approved is False
    assert report.broker_executable is False
    assert report == evaluate_p4_cost_regime_stress(
        compiled, audit, evidence, market, last_development_date=date(2025, 12, 31),
    )


def test_regime_is_prior_completed_bars_only(tmp_path: Path):
    *_, market = fixture(tmp_path)
    assert _lagged_regime(market, 63) is None
    assert _lagged_regime(market, 65)
    bars = list(market.bars)
    bars[100] = replace(bars[100], high=bars[100].close * 5, close=bars[100].close * 5)
    future_changed = replace(market, bars=tuple(bars))
    for i in (64, 80, 100):
        assert _lagged_regime(market, i) == _lagged_regime(future_changed, i)


def test_guard_against_wrong_source_and_non_development(tmp_path: Path):
    compiled, audit, evidence, market = fixture(tmp_path)
    for args in [
        (compiled, audit, {**evidence, "audit_hash": "0" * 64}, market),
        (compiled, audit, {**evidence, "measured_final_equity": 50}, market),
        (compiled, audit, evidence, replace(market, zone=DataZone.SEALED_OOS)),
        (compiled, audit, evidence, replace(market, zone=DataZone.VALIDATION)),
    ]:
        with pytest.raises(ResearchCatalogError):
            evaluate_p4_cost_regime_stress(
                *args, last_development_date=date(2025, 12, 31),
            )
    with pytest.raises(ResearchCatalogError, match="cutoff|2026"):
        evaluate_p4_cost_regime_stress(
            compiled, audit, evidence, market, last_development_date=date(2020, 12, 31),
        )

"""A lineage-audited inherited StrategyIR can be evaluated by year without OOS claims."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.algorithm_plan import compile_algorithm_plan
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.inherited_historical_robustness import (
    evaluate_inherited_historical_robustness,
)
from research.llm.inherited_feature_compiler import bind_inherited_features
from strategy_ir.schema import StrategyIR
from tests.research.test_academic_algorithm_plan import _catalog, _plan


def _market(change_late=False):
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(1050):
        dt = t0 + timedelta(days=i)
        price = 100 + i * 0.08 + 0.18 * (i % 31)
        if dt.year == 2022 and change_late:
            price += 25 * dt.timetuple().tm_yday / 365
        bars.append(Bar(dt, "QQQ", price, price + 1.0, price - 1.0, price, 50000))
    return MarketDataSet("inherited-replay-001", DataZone.DEVELOPMENT, tuple(bars))


def _compiled(catalog, market):
    base = compile_algorithm_plan(catalog, _plan(), market).compiled
    payload = base.strategy.model_dump(mode="json", by_alias=True)
    payload["exit"]["conditions"] = [{"op": "less_than", "left": "plan_vote_score", "value": 0.5}]
    payload["entry"]["conditions"] = [{"op": "greater_than", "left": "plan_entry", "value": 0.5}]
    child = StrategyIR.model_validate(payload)
    compiled = bind_inherited_features(base, child, market)
    audit = audit_inherited_decisions(compiled, market)
    evidence = {
        "generation": 64,
        "strategy_hash": compiled.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "audit_hash": audit.trace_hash,
        "measured_final_equity": audit.evaluation.final_equity,
        "metrics": audit.llm_packet["metrics"],
        "independent_oos_approved": False,
        "broker_executable": False,
        "evidence_hash": "a" * 64,
    }
    return compiled, evidence


def _report(cat, market, years=(2021, 2022), evidence_change=None):
    compiled, evidence = _compiled(cat, market)
    if evidence_change:
        evidence = {**evidence, **evidence_change}
    return evaluate_inherited_historical_robustness(
        compiled, evidence, market, years=years,
        last_development_date=date(2022, 12, 31)
    )


def test_inherited_yearly_report_is_reproducible_and_non_oos(tmp_path: Path):
    cat = _catalog(tmp_path)
    market = _market()
    result = _report(cat, market)
    assert result.strategy_hash
    assert result.full_audit_hash
    assert result.report_hash
    assert result.status == "INHERITED_IR_EX_POST_DEVELOPMENT_ONLY"
    assert result.selection_scope == "HISTORICALLY_EXPOSED_REPLAY_NOT_OOS"
    assert not result.broker_executable and not result.independent_oos_approved
    assert not result.candidate_promotable
    assert tuple(row.year for row in result.periods) == (2021, 2022)
    for row in result.periods:
        assert row.initial_cash == 10000
        assert row.first_holdout_equity == 10000
        assert row.first_fill is None or row.first_fill > row.period_first
        assert row.completed_trades <= row.fill_count
        assert row.market_qqq_costed_return > -1
        assert row.excess_costed_return == pytest.approx(
            row.total_return - row.market_qqq_costed_return
        )
    assert result == _report(cat, market)


def test_change_in_later_year_does_not_alter_prior_year_slice(tmp_path: Path):
    cat = _catalog(tmp_path)
    before = _report(cat, _market())
    after = _report(cat, _market(change_late=True))
    # The source audit/StrategyIR provenance hashes bind the full dataset, so
    # they legitimately change when a future price changes. Causal *economic*
    # outcomes in an earlier slice must remain identical nevertheless.
    for field in ("final_equity", "total_return", "max_drawdown", "fill_count",
                  "completed_trades", "paid_costs", "market_qqq_costed_return"):
        assert getattr(before.periods[0], field) == getattr(after.periods[0], field)
    assert before.periods[1].evaluation_hash != after.periods[1].evaluation_hash


@pytest.mark.parametrize("evidence_change", [
    {"strategy_hash": "b" * 64},
    {"audit_hash": "b" * 64},
    {"measured_final_equity": 1.0},
    {"independent_oos_approved": True},
    {"broker_executable": True},
    {"dataset_hash": "b" * 64},
    {"metrics": {"trade_count": 999}},
])
def test_rejects_forged_identity_or_claims(tmp_path: Path, evidence_change):
    with pytest.raises(ResearchCatalogError):
        _report(_catalog(tmp_path), _market(), evidence_change=evidence_change)


def test_rejects_sealed_future_or_unavailable_year(tmp_path: Path):
    cat = _catalog(tmp_path)
    market = _market()
    compiled, evidence = _compiled(cat, market)
    for bad in (
        replace(market, zone=DataZone.SEALED_OOS),
        replace(market, zone=DataZone.VALIDATION),
    ):
        with pytest.raises(ResearchCatalogError):
            evaluate_inherited_historical_robustness(
                compiled, evidence, bad, years=(2021,),
                last_development_date=date(2022, 12, 31)
            )
    with pytest.raises(ResearchCatalogError):
        evaluate_inherited_historical_robustness(
            compiled, evidence, market, years=(2023,),
            last_development_date=date(2023, 12, 31),
        )

"""V05: prove no cost/liquidity/multiple-search diagnostic is mistaken for PIT/OOS."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from core.data.contracts import DataZone, MarketDataSet
from core.data.parquet import ParquetDataProvider
from research.indicator_engine import cli
from research.indicator_engine.algorithm_plan import (
    compile_algorithm_plan,
    evaluate_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.development_economics_v05 import audit_development_economics
from research.indicator_engine.strategy_adapter import _COST
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


def _evaluated(tmp_path: Path):
    catalog, market, plan = _catalog(tmp_path), _market(), _plan()
    compiled = compile_algorithm_plan(catalog, plan, market)
    result = evaluate_algorithm_plan(catalog, compiled, market)
    assert result.trades_count > 0
    return market, result


def test_v05_real_cost_model_reconciles_fills_and_illustrative_cost_stress(tmp_path: Path):
    market, result = _evaluated(tmp_path)
    report = audit_development_economics(
        market, result, cost_model=_COST, max_daily_participation=0.01,
        stress_multiplier=2.0, attempted_trials=10,
    )
    assert report["status"] == "RESEARCH_ONLY_TRIAL_LEDGER_INCOMPLETE"
    assert report["fills_verified"] == result.trades_count
    assert report["baseline_paid_cost_usd"] == pytest.approx(result.total_paid_costs)
    assert report["hypothetical_extra_stress_cost_usd"] > 0
    assert report["stressed_net_pnl_proxy_usd"] < report["existing_costed_net_pnl_usd"]
    assert report["liquidity_daily_bar_ex_post_only"] is True
    assert report["trade_volume_capacity_passed"] is True
    assert report["full_trial_count_proven"] is False
    assert report["number_of_trials_declared"] == 10
    assert report["multiple_trial_statistical_significance_approved"] is False
    assert report["point_in_time_verified"] is False
    assert report["out_of_sample_approved"] is False
    assert report["broker_executable"] is False
    assert report == audit_development_economics(
        market, result, cost_model=_COST, max_daily_participation=0.01,
        stress_multiplier=2.0, attempted_trials=10,
    )


def test_v05_rejects_cost_consistent_fill_tampering_against_equity(tmp_path: Path) -> None:
    """A forged trade can conserve the fee sum yet not finance the equity."""
    market, actual = _evaluated(tmp_path)
    first = actual.trades[0]
    assert first.side == "buy"
    # All individual fill price, cost, quantity and notional checks pass.
    # The original equity hash is unchanged, so only independent cash/position
    # replay can detect that the buys no longer fund the claimed equity.
    smaller = replace(
        first, quantity=first.quantity / 2,
        notional=first.notional / 2, cost=first.cost / 2,
    )
    forged = replace(
        actual, trades=(smaller, *actual.trades[1:]),
        total_paid_costs=actual.total_paid_costs - first.cost / 2,
    )
    with pytest.raises(ResearchCatalogError, match="self-financing"):
        audit_development_economics(
            market, forged, cost_model=_COST, max_daily_participation=0.01,
            stress_multiplier=2, attempted_trials=10,
        )


def test_v05_replay_audit_is_explicit_in_report(tmp_path: Path) -> None:
    market, actual = _evaluated(tmp_path)
    report = audit_development_economics(
        market, actual, cost_model=_COST, max_daily_participation=0.01,
        stress_multiplier=2, attempted_trials=10,
    )
    assert report["self_financing_trade_equity_reconciled"] is True
    assert report["broker_executable"] is False


def test_cost_stress_higher_adds_cost_without_changing_backtest(tmp_path: Path):
    market, result = _evaluated(tmp_path)
    kwargs = dict(cost_model=_COST, max_daily_participation=0.01, attempted_trials=10)
    base = audit_development_economics(market, result, stress_multiplier=1.0, **kwargs)
    double = audit_development_economics(market, result, stress_multiplier=2.0, **kwargs)
    assert base["hypothetical_extra_stress_cost_usd"] == pytest.approx(0.0)
    assert double["hypothetical_extra_stress_cost_usd"] > 0
    assert base["existing_costed_net_pnl_usd"] == double["existing_costed_net_pnl_usd"]
    assert base["fixed_fill_stress_is_true_replayed_backtest"] is False


def test_small_participation_limit_blocks_capacity_promotion(tmp_path: Path):
    market, result = _evaluated(tmp_path)
    report = audit_development_economics(
        market, result, cost_model=_COST, max_daily_participation=1e-7,
        stress_multiplier=2, attempted_trials=5,
    )
    assert report["status"] == "EX_POST_VOLUME_PARTICIPATION_EXCEEDED"
    assert report["trade_volume_capacity_passed"] is False
    assert report["number_of_trade_dates_exceeding_capacity"] > 0
    assert report["broker_executable"] is False


def test_zero_volume_has_unknown_capacity_not_success(tmp_path: Path):
    market, result = _evaluated(tmp_path)
    execution_date = result.trades[0].timestamp
    bars = tuple(
        replace(bar, volume=0.0) if bar.timestamp.isoformat() == execution_date else bar
        for bar in market.bars
    )
    low_volume_market = MarketDataSet(market.version, market.zone, bars)
    (tmp_path / "zero").mkdir()
    cat = _catalog(tmp_path / "zero")
    compiled = compile_algorithm_plan(cat, _plan(), low_volume_market)
    recalculated = evaluate_algorithm_plan(cat, compiled, low_volume_market)
    report = audit_development_economics(
        low_volume_market, recalculated, cost_model=_COST,
        max_daily_participation=0.01, stress_multiplier=2, attempted_trials=2,
    )
    assert report["status"] == "INSUFFICIENT_DAILY_VOLUME_EVIDENCE"
    assert report["trade_volume_capacity_passed"] is False


@pytest.mark.parametrize("kind", [
    "sealed", "wrong_hash", "tamper_fee", "tamper_equity", "tamper_trade", "bad_stress",
    "bad_trial_count", "bad_participation", "invalid_cohort_length",
])
def test_fails_closed_on_invalid_inputs(tmp_path: Path, kind: str):
    market, result = _evaluated(tmp_path)
    args = {
        "cost_model": _COST, "max_daily_participation": 0.01,
        "stress_multiplier": 2.0, "attempted_trials": 10,
    }
    if kind == "sealed":
        market = replace(market, zone=DataZone.SEALED_OOS)
    elif kind == "wrong_hash":
        market = _market(change_last=True)
    elif kind == "tamper_fee":
        result = replace(result, total_paid_costs=0.0)
    elif kind == "tamper_equity":
        result = replace(result, equity_hash="0" * 64)
    elif kind == "tamper_trade":
        assert result.trades
        fake = replace(result.trades[0], notional=-100)
        result = replace(result, trades=(fake, *result.trades[1:]))
    elif kind == "bad_stress":
        args["stress_multiplier"] = 0.9
    elif kind == "bad_trial_count":
        args["attempted_trials"] = 0
    elif kind == "bad_participation":
        args["max_daily_participation"] = 1.1
    elif kind == "invalid_cohort_length":
        args["trial_returns"] = ((0.001,) * 30,) * 2
    with pytest.raises(ResearchCatalogError):
        audit_development_economics(market, result, **args)


def test_full_cohort_return_diagnostics_are_train_only(tmp_path: Path):
    market, result = _evaluated(tmp_path)
    returns = tuple(
        after / before - 1
        for before, after in zip(result.equity_curve, result.equity_curve[1:], strict=False)
    )
    report = audit_development_economics(
        market, result, cost_model=_COST, max_daily_participation=0.01,
        stress_multiplier=2.0, attempted_trials=2,
        trial_returns=(returns, tuple(-x / 2 for x in returns)),
    )
    assert report["cohort_dependence_status"] == "ESTIMATED_TRAIN_ONLY_COHORT"
    assert report["full_trial_count_proven"] is False
    assert report["iid_equivalent_trials_proxy"] is not None
    assert report["multiple_trial_statistical_significance_approved"] is False


def test_invalid_trial_history_is_not_accepted_as_full_search(tmp_path: Path):
    market, result = _evaluated(tmp_path)
    rets = tuple(
        after / before - 1
        for before, after in zip(result.equity_curve, result.equity_curve[1:], strict=False)
    )
    with pytest.raises(ResearchCatalogError):
        audit_development_economics(
            market, result, cost_model=_COST,
            max_daily_participation=0.01, stress_multiplier=2,
            attempted_trials=10, trial_returns=(rets, rets),
        )


def test_v05_cli_recompiles_canonical_development_results_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    catalog, market, plan = _catalog(tmp_path), _market(), _plan()
    source = tmp_path / "market.parquet"
    plan_file = tmp_path / "plan.json"
    ParquetDataProvider.write(source, market)
    plan_file.write_text(plan.model_dump_json(), encoding="utf-8")
    args = [
        "indicator-research", "--database", str(catalog.database),
        "audit-algorithm-economics", "--market-parquet", str(source),
        "--plan-json-file", str(plan_file),
        "--attempted-trials", "10", "--max-participation", "0.01",
        "--stress-multiplier", "2",
    ]
    monkeypatch.setattr(sys, "argv", args)
    assert cli.main() == 0
    accepted = json.loads(capsys.readouterr().out)
    assert accepted["market_hash"] == market.dataset_hash
    assert accepted["number_of_trials_declared"] == 10
    assert accepted["realizable_net_profit_verified"] is False
    assert accepted["broker_executable"] is False
    ParquetDataProvider.write(source, replace(market, zone=DataZone.SEALED_OOS))
    assert cli.main() == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["status"] == "DEVELOPMENT_ECONOMICS_REJECTED"
    assert blocked["broker_executable"] is False

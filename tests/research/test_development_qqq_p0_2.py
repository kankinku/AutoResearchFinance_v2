"""P0-2: cost-aligned, no-leverage QQQ benchmark development-only tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.data.contracts import DataZone
from research.indicator_engine.development_benchmark import (
    DevelopmentBenchmarkError,
    compare_qqq_development_benchmarks,
)
from tests.research.test_academic_algorithm_plan import _market


def test_costed_first_next_open_and_closed_bar_alignment():
    market = _market()
    q = compare_qqq_development_benchmarks(market)
    full = q["qqq_costed_buy_and_hold"]
    bars = market.bars
    cost_rate = 0.0008
    cash = 10_000.0
    expected_units = cash * (1 - cost_rate) / bars[1].open
    expected_end = expected_units * bars[-1].close
    assert full["final_equity"] == pytest.approx(expected_end, rel=1e-10)
    assert full["transaction_costs"] == pytest.approx(cash * cost_rate)
    assert full["first_eligible_execution_time"] == bars[1].timestamp.isoformat()
    assert q["dataset_hash"] == market.dataset_hash
    assert q["cost_policy"] == "academic-research-cost-v1"
    assert full["total_return"] == pytest.approx(expected_end / cash - 1)
    assert full["no_forced_final_liquidation"] is True


def test_costed_exposure_proxy_retains_idle_cash_and_one_initial_buy():
    market = _market()
    out = compare_qqq_development_benchmarks(market, realized_exposure=0.3)
    mixed = out["qqq_fixed_initial_allocation_proxy"]
    full = out["qqq_costed_buy_and_hold"]
    assert mixed["initial_qqq_fraction"] == pytest.approx(0.3)
    assert mixed["transaction_costs"] == pytest.approx(0.3 * full["transaction_costs"])
    assert mixed["final_equity"] == pytest.approx(7000 + 0.3 * full["final_equity"])
    assert mixed["total_return"] < full["total_return"]
    assert mixed["basis"] == "EX_POST_STRATEGY_EXPOSURE_INITIAL_ALLOCATION_PROXY"


def test_risk_matching_uses_realized_full_sample_returns_and_no_leverage():
    market = _market()
    whole = compare_qqq_development_benchmarks(market, include_equity_curve=True)
    qqq_curve = whole["qqq_costed_buy_and_hold"]["equity_curve"]
    equal = compare_qqq_development_benchmarks(
        market,
        strategy_equity_curve=qqq_curve,
        realized_exposure=0.6,
    )
    risk = equal["qqq_realized_volatility_matched_diagnostic"]
    assert risk["initial_qqq_fraction"] == pytest.approx(1.0, abs=1e-7)
    assert risk["daily_realized_volatility"] == pytest.approx(
        equal["strategy_daily_realized_volatility"], rel=1e-7
    )
    assert equal["independent_oos_approved"] is False
    assert equal["broker_executable"] is False
    assert risk["ex_post_hindsight_calibration"] is True
    assert risk["usable_for_live_selection"] is False


def test_zero_risk_leads_to_zero_allocation_and_no_trade_cost():
    market = _market()
    result = compare_qqq_development_benchmarks(
        market,
        strategy_equity_curve=(10000.0,) * len(market.bars),
        realized_exposure=0,
    )
    risk = result["qqq_realized_volatility_matched_diagnostic"]
    assert risk["initial_qqq_fraction"] == 0
    assert risk["final_equity"] == 10000
    assert risk["transaction_costs"] == 0


def test_bad_zone_symbol_alignment_and_future_access_are_rejected():
    market = _market()
    with pytest.raises(DevelopmentBenchmarkError, match="development"):
        compare_qqq_development_benchmarks(replace(market, zone=DataZone.SEALED_OOS))
    assert market.zone == DataZone.DEVELOPMENT
    with pytest.raises(DevelopmentBenchmarkError, match="QQQ"):
        compare_qqq_development_benchmarks(
            replace(market, bars=tuple(replace(bar, symbol="SPY") for bar in market.bars))
        )
    with pytest.raises(DevelopmentBenchmarkError, match="equity length"):
        compare_qqq_development_benchmarks(market, strategy_equity_curve=(10000.0,))
    with pytest.raises(DevelopmentBenchmarkError, match="exposure"):
        compare_qqq_development_benchmarks(market, realized_exposure=1.2)
    with pytest.raises(DevelopmentBenchmarkError, match="equity"):
        compare_qqq_development_benchmarks(
            market, strategy_equity_curve=(10000.0,) * (len(market.bars) - 1) + (float("nan"),)
        )


def test_qqq_only_is_precommitted_and_raw_price_returns_are_labeled():
    market = _market()
    result = compare_qqq_development_benchmarks(market)
    assert result["price_basis"] == "RAW_UNADJUSTED_PRICE_ONLY_NO_DIVIDEND_REINVESTMENT"
    assert result["no_cash_interest"] is True
    assert result["study_scope"] == "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
    assert "benchmark_verified" not in result or result["benchmark_verified"] is False
    assert result["qqq_realized_volatility_matched_diagnostic"] is None


def test_live_mcp_context_replays_latest_strategy_and_exposes_benchmark(tmp_path):
    from tests.integrations.test_academic_mcp_sessions import _setup
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    server, started = _setup(tmp_path)
    start = started["model_context"]["benchmark_comparison"]
    assert start["qqq_costed_buy_and_hold"]["transaction_costs"] > 0
    assert start["qqq_fixed_initial_allocation_proxy"] is None
    researcher = ScriptedResearcher()
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": researcher.propose(started["model_context"]),
        },
    )
    complete = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": researcher.propose(staged["model_context"]),
        },
    )
    comparison = complete["model_context"]["benchmark_comparison"]
    assert comparison["strategy_generation"] == 1
    assert comparison["qqq_costed_buy_and_hold"]["total_return"] == pytest.approx(
        start["qqq_costed_buy_and_hold"]["total_return"]
    )
    assert comparison["strategy_total_return"] == pytest.approx(
        complete["history"][-1]["metrics"]["total_return"]
    )
    assert comparison["qqq_fixed_initial_allocation_proxy"] is not None
    assert comparison["qqq_realized_volatility_matched_diagnostic"] is not None
    assert comparison["independent_oos_approved"] is False
    assert comparison["broker_executable"] is False
    assert complete["completed_generations"] == 1
    assert complete["checkpoint_phase"] == "AWAITING_PLAN"
    fetched = server._dispatch(
        "get_algorithm_research",
        {
            "session_id": started["session_id"],
        },
    )
    assert fetched["model_context"]["benchmark_comparison"] == comparison

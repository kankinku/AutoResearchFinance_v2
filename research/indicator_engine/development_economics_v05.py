"""V05: DEVELOPMENT-only trade capacity and multiple-search evidence audit.

Reconciles existing canonical costed fills to actual historical daily volume.
The original V05 report is a *fixed-fill proxy*. Explicit opt-in separately
replays the canonical engine; neither result is an executable forecast.
Full-day market volume was unavailable at open; this is ex-post diagnostics.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from math import isclose, isfinite
from typing import Any

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.costs.model import CostModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from evaluation.trial_dependence import estimate_cohort_dependence
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.strategy_adapter import (
    AcademicDevelopmentResult,
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)


def audit_development_economics(
    market: MarketDataSet,
    result: AcademicDevelopmentResult,
    *,
    cost_model: CostModel,
    max_daily_participation: float,
    stress_multiplier: float,
    attempted_trials: int,
    trial_returns: tuple[tuple[float, ...], ...] | None = None,
) -> dict[str, Any]:
    """Retrospective pre-T4 diagnostic on a canonical, costed DEVELOPMENT run.

    A self-reported trial count cannot attest an exhaustive search. The optional
    return cohort is analyzed using the EXISTING bounded training-only trial
    dependence estimator; it does not qualify multiple-testing significance.
    """
    if (
        market.zone is not DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or len(market.bars) < 2
        or len({b.symbol for b in market.bars}) != 1
        or result.status != "NON_PIT_DEVELOPMENT_RESULT"
        or result.dataset_hash != market.dataset_hash
        or result.broker_executable is not False
        or result.candidate_promotable is not False
        or result.out_of_sample_approved is not False
    ):
        raise ResearchCatalogError("V05 accepts only canonical development-only results")
    if (
        not isfinite(max_daily_participation)
        or not 0 < max_daily_participation <= 1.0
        or not isfinite(stress_multiplier)
        or stress_multiplier < 1.0
        or type(attempted_trials) is not int
        or not 1 <= attempted_trials <= 100_000
    ):
        raise ResearchCatalogError("unbounded cost stress, participation or trials")
    if (
        result.trades_count != len(result.trades)
        or len(result.equity_curve) != len(market.bars)
        or not result.equity_curve
        or any(not isfinite(v) or v <= 0 for v in result.equity_curve)
        or not isfinite(result.initial_cash) or result.initial_cash <= 0
        or not isclose(result.equity_curve[0], result.initial_cash, rel_tol=1e-10)
        or not isclose(result.equity_curve[-1], result.final_equity, rel_tol=1e-10)
        or content_hash(result.equity_curve) != result.equity_hash
        or not isfinite(result.total_paid_costs)
    ):
        raise ResearchCatalogError("canonical result cash/equity/trace integrity invalid")

    bars = {bar.timestamp.isoformat(): bar for bar in market.bars}
    volume_by_date: dict[str, float] = defaultdict(float)
    initial_total = 0.0
    stressed_total = 0.0
    for trade in result.trades:
        bar = bars.get(trade.timestamp)
        if (
            bar is None or trade.symbol != bar.symbol
            or trade.side not in ("buy", "sell")
            or any(
                not isfinite(v) or v < 0
                for v in (trade.notional, trade.cost, trade.quantity)
            )
            or trade.quantity <= 0
            or not isclose(trade.price, bar.open, rel_tol=1e-9)
            or not isclose(
                trade.notional, trade.quantity * trade.price,
                rel_tol=1e-9, abs_tol=1e-8,
            )
        ):
            raise ResearchCatalogError("V05 canonical next-open fill mismatch")
        # Canonical buy-side engine deducts cost from the cash allocation
        # BEFORE constructing the recorded shares. Recorded buy notional is
        # consequently NET of the input gross cost. Sell notional is gross.
        unit_rate = cost_model.calculate(
            1.0, side=trade.side, stress_multiplier=1.0,
        ).total
        if unit_rate >= 1.0:
            raise ResearchCatalogError("execution cost exceeds 100% of gross allocation")
        charged_notional = (
            trade.notional / (1.0 - unit_rate)
            if trade.side == "buy" else trade.notional
        )
        baseline_cost = cost_model.calculate(
            charged_notional, side=trade.side, stress_multiplier=1.0,
        ).total
        if not isclose(trade.cost, baseline_cost, rel_tol=1e-8, abs_tol=1e-6):
            raise ResearchCatalogError("canonical cost model/version mismatch")
        initial_total += baseline_cost
        stressed_total += cost_model.calculate(
            charged_notional, side=trade.side,
            stress_multiplier=stress_multiplier,
        ).total
        volume_by_date[trade.timestamp] += trade.quantity
    if not isclose(
        result.total_paid_costs, initial_total, rel_tol=1e-8, abs_tol=1e-6,
    ):
        raise ResearchCatalogError("canonical total cost evidence mismatch")

    missing_liquidity = [
        key for key, quantity in volume_by_date.items()
        if bars[key].volume <= 0 or not isfinite(quantity)
    ]
    ratios = [
        quantity / bars[key].volume for key, quantity in volume_by_date.items()
        if bars[key].volume > 0
    ]
    exceeded = sum(
        (quantity / bars[key].volume) > max_daily_participation
        for key, quantity in volume_by_date.items()
        if bars[key].volume > 0
    )
    if not volume_by_date:
        status = "NO_FILLS_CAPACITY_UNMEASURABLE"
    elif missing_liquidity:
        status = "INSUFFICIENT_DAILY_VOLUME_EVIDENCE"
    elif exceeded:
        status = "EX_POST_VOLUME_PARTICIPATION_EXCEEDED"
    else:
        status = "RESEARCH_ONLY_TRIAL_LEDGER_INCOMPLETE"

    cohort_status = "NOT_EVALUATED_FULL_TRIAL_LEDGER_MISSING"
    rank: float | None = None
    iid_proxy: float | None = None
    if trial_returns is not None:
        if len(trial_returns) != attempted_trials or attempted_trials > 128:
            raise ResearchCatalogError("incomplete or unbounded explored return cohort")
        if any(len(row) != len(market.bars) - 1 for row in trial_returns):
            raise ResearchCatalogError("unaligned development trial returns")
        cohort = estimate_cohort_dependence(
            trial_returns, training_cutoff_at=market.bars[-1].timestamp.isoformat(),
        )
        if cohort.status in {
            "MISALIGNED_RETURNS", "INVALID_RETURN_OBSERVATIONS",
            "INVALID_CORRELATION", "INVALID_NULL_REFERENCE",
            "COHORT_LIMIT_EXCEEDED",
        }:
            raise ResearchCatalogError("invalid cohort dependence evidence")
        cohort_status = cohort.status
        rank = cohort.effective_rank
        iid_proxy = cohort.iid_equivalent_trials_estimate
    extra = max(0.0, stressed_total - initial_total)
    report: dict[str, Any] = {
        "schema": "v05-development-net-capacity-search-diagnostic-v1",
        "status": status,
        "market_hash": market.dataset_hash,
        "result_strategy_hash": result.strategy_hash,
        "equity_hash": result.equity_hash,
        "cost_model_version": cost_model.version,
        "fills_verified": len(result.trades),
        "existing_costed_net_pnl_usd": result.final_equity - result.initial_cash,
        "baseline_paid_cost_usd": initial_total,
        "stress_multiplier": stress_multiplier,
        "hypothetical_extra_stress_cost_usd": extra,
        "stressed_net_pnl_proxy_usd": (
            result.final_equity - result.initial_cash - extra
        ),
        "fixed_fill_stress_is_true_replayed_backtest": False,
        "volume_proxy_max_participation": max_daily_participation,
        "max_observed_daily_volume_fraction": (
            max(ratios) if ratios and not missing_liquidity else None
        ),
        "number_of_trade_dates_exceeding_capacity": exceeded,
        "trade_volume_capacity_passed": (
            bool(volume_by_date) and not missing_liquidity and exceeded == 0
        ),
        "liquidity_daily_bar_ex_post_only": True,
        "volume_known_at_next_open": False,
        "order_book_spread_depth_and_impact_verified": False,
        "number_of_trials_declared": attempted_trials,
        "trial_count_source": "CALLER_SUPPLIED_UNATTESTED",
        "full_trial_count_proven": False,
        "cohort_dependence_status": cohort_status,
        "iid_equivalent_trials_proxy": iid_proxy,
        "entropy_effective_rank_proxy": rank,
        "multiple_trial_statistical_significance_approved": False,
        "point_in_time_verified": False,
        "out_of_sample_approved": False,
        "realizable_net_profit_verified": False,
        "broker_executable": False,
        "next_stage": "T4_REAL_CHATGPT_MCP_10_THEN_100_GENERATIONS",
    }
    report["report_hash"] = content_hash(report)
    return report


def audit_replayed_development_cost_stress(
    market: MarketDataSet,
    result: AcademicDevelopmentResult,
    compiled: CompiledAcademicStrategy,
    *,
    cost_model: CostModel,
    max_daily_participation: float,
    stress_multiplier: float,
    attempted_trials: int,
    trial_returns: tuple[tuple[float, ...], ...] | None = None,
) -> dict[str, Any]:
    """Re-run the exact verified DEVELOPMENT strategy with stressed execution costs.

    The existing fixed-fill V05 report remains unchanged. This separate report
    measures executed trades and equity from the canonical engine, not a
    subtraction from the original result. Neither is a PIT/OOS certificate.
    """
    proxy = audit_development_economics(
        market,
        result,
        cost_model=cost_model,
        max_daily_participation=max_daily_participation,
        stress_multiplier=stress_multiplier,
        attempted_trials=attempted_trials,
        trial_returns=trial_returns,
    )
    if not proxy["trade_volume_capacity_passed"]:
        raise ResearchCatalogError("V05 replay blocked by unverified daily liquidity")
    if compiled.strategy_hash != result.strategy_hash:
        raise ResearchCatalogError("V05 replay strategy hash mismatch")

    # Verify that the supplied historic result is a true evaluation of this
    # exact compiled strategy, dataset, initial cash and canonical cost model.
    baseline = evaluate_compiled_development(
        compiled, market, initial_cash=result.initial_cash,
    )
    if baseline != result:
        raise ResearchCatalogError("V05 baseline differs from canonical compiled replay")

    try:
        replay = BacktestEngine().run(
            BacktestRequest(
                run_id="v05-cost-replay-" + compiled.strategy_hash[:16],
                strategy_hash=compiled.strategy_hash,
                dataset=market,
                initial_cash=result.initial_cash,
                strategy=compiled.strategy,
                cost_model=cost_model,
                feature_values=compiled.feature_values,
                feature_values_pre_lagged=True,
                cost_stress_multiplier=stress_multiplier,
            )
        )
    except ValueError as exc:
        raise ResearchCatalogError("V05 stressed execution rejected by canonical engine") from exc
    if (
        replay.exit_status != "SUCCEEDED"
        or replay.data_hash != market.dataset_hash
        or replay.strategy_hash != compiled.strategy_hash
        or len(replay.equity_curve) != len(market.bars)
        or content_hash(replay.equity_curve) != replay.equity_curve_hash
        or not all(isfinite(value) and value > 0 for value in replay.equity_curve)
    ):
        raise ResearchCatalogError("V05 stressed canonical result integrity failure")

    bars = {bar.timestamp.isoformat(): bar for bar in market.bars}
    volume_by_date: dict[str, float] = defaultdict(float)
    stressed_total_costs = 0.0
    for trade in replay.trades:
        bar = bars.get(trade.timestamp)
        if (
            bar is None or trade.symbol != bar.symbol
            or trade.side not in ("buy", "sell")
            or trade.quantity <= 0
            or not isclose(trade.price, bar.open, rel_tol=1e-9)
            or not isfinite(trade.cost) or trade.cost < 0
        ):
            raise ResearchCatalogError("V05 stressed fill is not a canonical next-open trade")
        volume_by_date[trade.timestamp] += trade.quantity
        stressed_total_costs += trade.cost
    if (
        not volume_by_date
        or any(
            bars[key].volume <= 0
            or quantity / bars[key].volume > max_daily_participation
            for key, quantity in volume_by_date.items()
        )
    ):
        raise ResearchCatalogError("V05 stressed replay failed volume capacity gate")

    peak = result.initial_cash
    max_drawdown = 0.0
    for equity in replay.equity_curve:
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, 100.0 * (peak - equity) / peak)
    net_pnl = replay.equity_curve[-1] - result.initial_cash
    report: dict[str, Any] = {
        "schema": "v05-canonical-cost-stress-replay-v1",
        "status": "DEVELOPMENT_ONLY_REPLAY",
        "canonical_backtest_rerun": True,
        "market_hash": market.dataset_hash,
        "strategy_hash": compiled.strategy_hash,
        "baseline_equity_hash": result.equity_hash,
        "replay_equity_hash": replay.equity_curve_hash,
        "replay_fill_trace_hash": content_hash([asdict(trade) for trade in replay.trades]),
        "cost_model_version": cost_model.version,
        "cost_policy_hash": content_hash({
            "version": cost_model.version,
            "commission_bps": cost_model.commission_bps,
            "spread_bps": cost_model.spread_bps,
            "slippage": {"basis_points": cost_model.slippage.basis_points},
            "multiplier": stress_multiplier,
        }),
        "stress_multiplier": stress_multiplier,
        "baseline_report_hash": proxy["report_hash"],
        "baseline_trade_count": result.trades_count,
        "replay_trade_count": len(replay.trades),
        "replay_total_paid_costs_usd": stressed_total_costs,
        "replay_net_pnl_usd": net_pnl,
        "replay_max_drawdown_pct": max_drawdown,
        "proxy_net_pnl_usd": proxy["stressed_net_pnl_proxy_usd"],
        "replay_minus_proxy_usd": net_pnl - proxy["stressed_net_pnl_proxy_usd"],
        "replay_trade_volume_capacity_passed": True,
        "trials_declared_unattested": attempted_trials,
        "cohort_dependence_status": proxy["cohort_dependence_status"],
        "iid_equivalent_trials_proxy": proxy["iid_equivalent_trials_proxy"],
        "full_trial_count_proven": False,
        "multiple_trial_statistical_significance_approved": False,
        "volume_known_at_next_open": False,
        "point_in_time_verified": False,
        "out_of_sample_approved": False,
        "realizable_net_profit_verified": False,
        "candidate_promotable": False,
        "broker_executable": False,
    }
    report["report_hash"] = content_hash(report)
    return report

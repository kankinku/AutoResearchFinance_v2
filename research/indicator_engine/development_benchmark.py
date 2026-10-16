"""P0-2: QQQ benchmarks computed on the exact academic development bars.

Long-only cash-and-QQQ single buy at the first next-open opportunity; the same
canonical academic fee model is applied. These are historical price-only
*diagnostics*, neither PIT nor total-return/OOS proof or tradable predictions.
"""

from __future__ import annotations

from math import isfinite
from statistics import pstdev
from typing import Any

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from research.indicator_engine.strategy_adapter import _COST


class DevelopmentBenchmarkError(ValueError):
    """Reject unsupported data, prices, risk budgets or misleading comparisons."""


def _daily_vol(curve: tuple[float, ...]) -> float:
    return pstdev(tuple(b / a - 1 for a, b in zip(curve, curve[1:], strict=False)))


def _curve(market: MarketDataSet, cash: float, fraction: float) -> tuple[tuple[float, ...], float]:
    if not 0 <= fraction <= 1:
        raise DevelopmentBenchmarkError("benchmark fraction must be between zero and one")
    allocated = cash * fraction
    cost = _COST.calculate(allocated, side="buy", stress_multiplier=1.0).total
    shares = (allocated - cost) / market.bars[1].open
    remaining = cash - allocated
    # A rule at the first completed close can only execute at the NEXT open.
    # Prior to that open: account still holds exactly 100% idle cash.
    curve = (cash,) + tuple(remaining + shares * b.close for b in market.bars[1:])
    if min(curve) <= 0 or any(not isfinite(x) for x in curve):
        raise DevelopmentBenchmarkError("invalid benchmark equity")
    return curve, cost


def _summarize(
    market: MarketDataSet,
    cash: float,
    fraction: float,
    basis: str,
    *,
    include_equity_curve: bool,
) -> dict[str, Any]:
    curve, cost = _curve(market, cash, fraction)
    m = calculate_metrics(curve, (), periods_per_year=252.0)
    summary: dict[str, Any] = {
        "basis": basis,
        "initial_qqq_fraction": fraction,
        "total_return": m.total_return,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "max_drawdown": m.max_drawdown,
        "calmar": m.calmar,
        "initial_equity": cash,
        "final_equity": curve[-1],
        "transaction_costs": cost,
        "equity_curve_hash": content_hash(curve),
        "first_eligible_execution_time": market.bars[1].timestamp.isoformat(),
        "no_forced_final_liquidation": True,
    }
    if include_equity_curve:
        summary["equity_curve"] = curve
    return summary


def compare_qqq_development_benchmarks(
    market: MarketDataSet,
    *,
    initial_cash: float = 10_000.0,
    strategy_equity_curve: tuple[float, ...] | None = None,
    realized_exposure: float | None = None,
    include_equity_curve: bool = False,
) -> dict[str, Any]:
    """Aligned, costed B&H + descriptive initial exposure/risk matched proxies.

    Exposure and realized-vol matching are *post hoc* summaries of the same
    reused development period. They are NOT feasible forward-trading rules and
    may not be used for promotion or multiple testing.
    """
    if market.zone != DataZone.DEVELOPMENT or market.timeframe != "1d" or len(market.bars) < 3:
        raise DevelopmentBenchmarkError("daily development bars required")
    if any(bar.symbol != "QQQ" for bar in market.bars):
        raise DevelopmentBenchmarkError("QQQ single-symbol bars required")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise DevelopmentBenchmarkError("invalid positive starting capital")
    if realized_exposure is not None and (
        not isfinite(realized_exposure) or not 0 <= realized_exposure <= 1
    ):
        raise DevelopmentBenchmarkError("exposure must be between zero and one")
    strategy_vol: float | None = None
    if strategy_equity_curve is not None:
        if len(strategy_equity_curve) != len(market.bars):
            raise DevelopmentBenchmarkError("strategy equity length must match all bars")
        if any(not isfinite(v) or v <= 0 for v in strategy_equity_curve):
            raise DevelopmentBenchmarkError("strategy equity must be finite and positive")
        if abs(strategy_equity_curve[0] - initial_cash) > 1e-7 * initial_cash:
            raise DevelopmentBenchmarkError("strategy and benchmark initial capital mismatch")
        strategy_vol = _daily_vol(strategy_equity_curve)
    bh = _summarize(
        market,
        initial_cash,
        1.0,
        "COSTED_NEXT_OPEN_SINGLE_BUY_HOLD",
        include_equity_curve=include_equity_curve,
    )
    proxy = None
    if realized_exposure is not None:
        proxy = _summarize(
            market,
            initial_cash,
            realized_exposure,
            "EX_POST_STRATEGY_EXPOSURE_INITIAL_ALLOCATION_PROXY",
            include_equity_curve=include_equity_curve,
        )
    risk = None
    if strategy_vol is not None:
        full_curve, _ = _curve(market, initial_cash, 1.0)
        max_vol = _daily_vol(full_curve)
        if strategy_vol <= 0:
            fraction = 0.0
            limited = False
        elif strategy_vol >= max_vol:
            fraction = 1.0
            limited = strategy_vol > max_vol + 1e-12
        else:
            low, high = 0.0, 1.0
            for _ in range(45):
                mid = (low + high) / 2
                candidate, _ = _curve(market, initial_cash, mid)
                if _daily_vol(candidate) < strategy_vol:
                    low = mid
                else:
                    high = mid
            fraction = (low + high) / 2
            limited = False
        risk = _summarize(
            market,
            initial_cash,
            fraction,
            "EX_POST_REALIZED_VOLATILITY_MATCHED_PROXY",
            include_equity_curve=include_equity_curve,
        )
        curve, _ = _curve(market, initial_cash, fraction)
        risk.update(
            {
                "daily_realized_volatility": _daily_vol(curve),
                "target_daily_realized_volatility": strategy_vol,
                "volatility_match_capped_no_leverage": limited,
                "ex_post_hindsight_calibration": True,
                "usable_for_live_selection": False,
            }
        )
    return {
        "schema": "p0-qqq-development-benchmark-v1",
        "dataset_hash": market.dataset_hash,
        "study_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        "price_basis": "RAW_UNADJUSTED_PRICE_ONLY_NO_DIVIDEND_REINVESTMENT",
        "cost_policy": _COST.version,
        "no_cash_interest": True,
        "qqq_costed_buy_and_hold": bh,
        "qqq_fixed_initial_allocation_proxy": proxy,
        "qqq_realized_volatility_matched_diagnostic": risk,
        "strategy_daily_realized_volatility": strategy_vol,
        "benchmark_verified": False,
        "independent_oos_approved": False,
        "broker_executable": False,
        "research_conclusions": "DESCRIPTIVE_ONLY_NOT_FORWARD_TESTED",
    }

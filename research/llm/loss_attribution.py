"""P2-1: Evidence-grounded *observations* for the next GPT research plan.

Losses are not labeled with proven causes. This module neither performs
counterfactual trades nor fits an LLM. It exposes bounded hypotheses to test
against the unchanged strategy using the existing MCP + S7 experiment gate.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from math import isfinite
from typing import Any

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.decision_audit import AcademicDecisionAudit, calculate_audit_hash


class LossAttributionError(ValueError):
    """Invalid development evidence must never reach the GPT research context."""


# Observation-only codes: directions are *not* profitable trading rules.
_TESTS: dict[str, tuple[str, str, str]] = {
    "NO_BREAKOUT_AT_ENTRY": (
        "previous_range_breakout",
        "Test a breakout-confirmation entry rule as a single-rule ablation; "
        "compare excluded winning trades as well as whipsaw losses.",
        "Adding breakout confirmation may miss early trend winners and reduce exposure.",
    ),
    "EMA_TURNED_OFF_BY_EXIT": (
        "ema_direction_20",
        "Compare an EMA-sensitive exit with a slower exit using unchanged parent and fees.",
        "A quicker exit may truncate profitable rebounds and increase churn.",
    ),
    "MOMENTUM_TURNED_OFF_BY_EXIT": (
        "time_series_momentum",
        "Ablate the momentum confirmation or vary its role only with a paired control.",
        "Removing momentum confirmation can increase false entries or market exposure.",
    ),
    "PARKINSON_VARIANCE_ROSE_DURING_HOLD": (
        "parkinson_variance",
        "Test a volatility regime gate independently of exit-rule changes.",
        "Volatility restriction can exclude strong trends and reduce returns.",
    ),
    "REGIME_GATE_TURNED_OFF": (
        "plan_regime",
        "Compare regime-gate ablation versus unchanged strategy with per-regime trade counts.",
        "Ablating a regime gate may increase drawdown in stressed markets.",
    ),
    "EXIT_BELOW_OBSERVED_CLOSE_PEAK": (
        "plan_vote_score",
        "Compare a single exit-threshold change for turnover, return and maximum drawdown.",
        "A more sensitive exit may cause whipsaw; observed peak uses hindsight.",
    ),
    "COST_EXCEEDS_POSITIVE_GROSS_PNL": (
        "transaction_costs",
        "Test turnover reduction without altering the canonical cost model.",
        "Fewer trades may also discard positive gross opportunities.",
    ),
}


def _checked(audit: AcademicDecisionAudit, market: MarketDataSet) -> None:
    if market.zone != DataZone.DEVELOPMENT:
        raise LossAttributionError("only development market data is supported")
    if (
        audit.status != "RESEARCH_DECISION_AUDIT_ONLY"
        or audit.broker_executable is not False
        or audit.point_in_time_verified is not False
        or audit.candidate_promotable is not False
        or audit.evaluation.dataset_hash != market.dataset_hash
        or audit.llm_packet.get("audit_hash") != audit.trace_hash
        or audit.trace_hash
        != calculate_audit_hash(
            audit.evaluation,
            audit.decisions,
            audit.fills,
            audit.round_trips,
            audit.llm_packet,
        )
        or len(audit.decisions) != len(market.bars)
        or audit.evaluation.equity_hash != content_hash(audit.evaluation.equity_curve)
    ):
        raise LossAttributionError("audit evidence hash/dataset/alignment mismatch")
    if any(audit.decisions[i].signal_time != bar.timestamp for i, bar in enumerate(market.bars)):
        raise LossAttributionError("audit decision-to-bar timestamp mismatch")


def _number(source: Mapping[str, float | None], key: str) -> float | None:
    value = source.get(key)
    return (
        float(value)
        if isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value)
        else None
    )


def _trade_case(
    trade: Any,
    *,
    by_decision: Mapping[str, Any],
    market: MarketDataSet,
) -> dict[str, Any]:
    entry = by_decision[trade.entry_fill.decision_id]
    exit_point = by_decision[trade.exit_fill.decision_id]
    if (
        entry.action != "REQUEST_ENTRY"
        or exit_point.action != "REQUEST_EXIT"
        or entry.bar_index >= trade.entry_fill.bar_index
        or exit_point.bar_index >= trade.exit_fill.bar_index
        or trade.entry_fill.bar_index >= trade.exit_fill.bar_index
    ):
        raise LossAttributionError("audit entry/exit decision chain mismatch")
    ei, xi = dict(entry.indicator_values), dict(exit_point.indicator_values)
    applied_entry = trade.entry_fill.trade
    applied_exit = trade.exit_fill.trade
    gross = applied_exit.notional - applied_entry.notional
    costs = applied_entry.cost + applied_exit.cost
    if abs((gross - costs) - trade.net_pnl) > 1e-6:
        raise LossAttributionError("signed trade PnL and canonical costs mismatch")
    if applied_entry.price <= 0 or applied_exit.price <= 0:
        raise LossAttributionError("nonpositive trade execution price")
    observed_closes = [
        market.bars[i].close
        for i in range(trade.entry_fill.bar_index, trade.exit_fill.bar_index + 1)
    ]
    if not observed_closes or any(not isfinite(x) or x <= 0 for x in observed_closes):
        raise LossAttributionError("invalid close prices in held market bars")
    close_peak_giveback = max(
        0.0, (max(observed_closes) - applied_exit.price) / applied_entry.price
    )
    codes: list[str] = []
    if (breakout := _number(ei, "previous_range_breakout")) is not None and breakout <= 0.5:
        codes.append("NO_BREAKOUT_AT_ENTRY")
    ema_start, ema_end = _number(ei, "ema_direction_20"), _number(xi, "ema_direction_20")
    if ema_start is not None and ema_end is not None and ema_start > 0.5 >= ema_end:
        codes.append("EMA_TURNED_OFF_BY_EXIT")
    momentum_start = _number(ei, "time_series_momentum")
    momentum_end = _number(xi, "time_series_momentum")
    if (
        momentum_start is not None
        and momentum_end is not None
        and momentum_start > 0.5 >= momentum_end
    ):
        codes.append("MOMENTUM_TURNED_OFF_BY_EXIT")
    vol_start, vol_end = _number(ei, "parkinson_variance"), _number(xi, "parkinson_variance")
    if (
        vol_start is not None
        and vol_end is not None
        and vol_start > 0
        and vol_end >= 1.5 * vol_start
    ):
        codes.append("PARKINSON_VARIANCE_ROSE_DURING_HOLD")
    gate_begin = dict(entry.evaluated_gates).get("regime_positive")
    gate_end = dict(exit_point.evaluated_gates).get("regime_positive")
    if gate_begin is True and gate_end is False:
        codes.append("REGIME_GATE_TURNED_OFF")
    if close_peak_giveback >= 0.03:
        codes.append("EXIT_BELOW_OBSERVED_CLOSE_PEAK")
    if gross > 0 and costs >= gross:
        codes.append("COST_EXCEEDS_POSITIVE_GROSS_PNL")
    if not codes:
        codes.append("NO_SPECIFIC_PATTERN_OBSERVED")
    return {
        "trade_id": trade.trade_id,
        "entry_decision_id": entry.decision_id,
        "exit_decision_id": exit_point.decision_id,
        "entry_signal_time": entry.signal_time.isoformat(),
        "exit_signal_time": exit_point.signal_time.isoformat(),
        "entry_execution_time": trade.entry_fill.execution_time.isoformat(),
        "exit_execution_time": trade.exit_fill.execution_time.isoformat(),
        "held_bars": trade.exit_fill.bar_index - trade.entry_fill.bar_index,
        "net_pnl": trade.net_pnl,
        "price_pnl_before_cost": gross,
        "cost_paid": costs,
        "close_peak_giveback_fraction": close_peak_giveback,
        "entry_indicator_values": ei,
        "exit_indicator_values": xi,
        "entry_gates": dict(entry.evaluated_gates),
        "exit_gates": dict(exit_point.evaluated_gates),
        "observation_codes": codes,
        "observation_not_causal_proof": True,
    }


def build_loss_attribution(
    audit: AcademicDecisionAudit,
    market: MarketDataSet,
    *,
    max_cases: int = 8,
) -> dict[str, Any]:
    """Expose loss/winner observations and bounded *suggested* counter-experiments.

    Hindsight marks are only descriptions of completed trades, never features
    of the next-open decision engine, training labels, or performance forecasts.
    """
    if type(max_cases) is not int or not 1 <= max_cases <= 12:
        raise LossAttributionError("bounded sample size must be 1..12")
    _checked(audit, market)
    by_decision = {point.decision_id: point for point in audit.decisions}
    losses = sorted(
        (t for t in audit.round_trips if t.net_pnl < 0), key=lambda x: (x.net_pnl, x.trade_id)
    )
    winners = sorted(
        (t for t in audit.round_trips if t.net_pnl > 0), key=lambda x: (-x.net_pnl, x.trade_id)
    )
    cases = [_trade_case(t, by_decision=by_decision, market=market) for t in losses[:max_cases]]
    controls = [_trade_case(t, by_decision=by_decision, market=market) for t in winners[:max_cases]]
    counts = Counter(code for x in cases for code in x["observation_codes"])
    winner_counts = Counter(code for x in controls for code in x["observation_codes"])

    # Compare *observations* against selected winning controls before proposing
    # an action. This is NOT a matched cohort nor a significant risk ratio.
    def rank_observation(item: tuple[str, int]) -> tuple[float, int, str]:
        code, loss_count = item
        observed_loss_frequency = loss_count / len(cases) if cases else 0.0
        observed_win_frequency = winner_counts[code] / len(controls) if controls else 0.0
        return (-(observed_loss_frequency - observed_win_frequency), -loss_count, code)

    suggestions = []
    for code, count in sorted(counts.items(), key=rank_observation):
        if code not in _TESTS:
            continue
        indicator, description, alternative = _TESTS[code]
        source_ids = [x["trade_id"] for x in cases if code in x["observation_codes"]]
        suggestions.append(
            {
                "kind": "RECOMMEND_TEST_ONLY",
                "observation_code": code,
                "indicator_or_metric": indicator,
                "observed_loss_cases": count,
                "evidence_trade_ids": source_ids[:max_cases],
                "proposed_test": description,
                "alternative_explanation": alternative,
                "control": "PARENT_UNCHANGED",
                "required_metrics": [
                    "total_return",
                    "max_drawdown",
                    "trade_count",
                    "exposure",
                    "transaction_costs",
                ],
                "test_result": "NOT_RUN",
                "causal_status": "NOT_ESTABLISHED",
            }
        )
        if len(suggestions) >= 4:
            break
    body: dict[str, Any] = {
        "schema": "observed-loss-attribution-p2-1-v1",
        "source_audit_hash": audit.trace_hash,
        "strategy_hash": audit.evaluation.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "closed_trade_count": len(audit.round_trips),
        "losing_closed_trade_count": len(losses),
        "loss_cases": cases,
        "winner_controls": [
            {**x, "selection_method": "TOP_POSITIVE_PNL_NOT_MATCHED_CONTROL"} for x in controls
        ],
        "observation_counts_in_sample": dict(sorted(counts.items())),
        "winner_observation_counts_in_sample": dict(sorted(winner_counts.items())),
        "test_suggestions": suggestions,
        "no_inferred_proven_cause": True,
        "hindsight_review_only": True,
        "selection_bias_notice": "Both loss and winner examples are ex-post development selections",
        "causal_status": "NOT_ESTABLISHED",
        "independent_oos_approved": False,
        "broker_executable": False,
        "execution_policy": "GPT_MCP_PROPOSAL_ONLY_NOT_AUTO_APPLIED",
    }
    return {**body, "evidence_hash": content_hash(body)}

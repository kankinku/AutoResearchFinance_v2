"""F3: non-promoting, costed, same-parent S7 contribution review.

Use canonical executed fills and actual equity paths. Parent-only losing entries
are NOT 'saved losses'; parent-only winning entries are NOT proved child missed
profit. Both labels are ex-post comparisons of different portfolio histories.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from research.indicator_engine.controlled_experiments import (
    ControlledExperimentReport,
    _development_windows,
    _execution_delta,
)
from research.indicator_engine.decision_audit import AcademicDecisionAudit
from research.indicator_engine.development_benchmark import compare_qqq_development_benchmarks
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy
from research.llm.loss_attribution import LossAttributionError, _checked


class ContributionEvidenceError(ValueError):
    """Invalid or forged development comparison must not become GPT advice."""


def _held_fraction(audit: AcademicDecisionAudit, market: MarketDataSet) -> float:
    """Actual cash/long position at successive close marks, not signal frequency."""
    executed = {fill.execution_time: fill.side for fill in audit.fills}
    if len(executed) != len(audit.fills):
        raise ContributionEvidenceError("duplicate fill time in contribution")
    holding = False
    holding_bars = 0
    for bar in market.bars[1:]:
        side = executed.get(bar.timestamp)
        if side == "buy":
            if holding:
                raise ContributionEvidenceError("unpaired long entry")
            holding = True
        elif side == "sell":
            if not holding:
                raise ContributionEvidenceError("unpaired long exit")
            holding = False
        elif side is not None:
            raise ContributionEvidenceError("unsupported fill side")
        holding_bars += int(holding)
    if not market.bars[1:]:
        raise ContributionEvidenceError("empty measured exposure")
    if any(
        fill.execution_time not in {bar.timestamp for bar in market.bars[1:]}
        for fill in audit.fills
    ):
        raise ContributionEvidenceError("unmatched executed bar")
    return holding_bars / (len(market.bars) - 1)


def _entry_cases(
    audit: AcademicDecisionAudit,
    opposite_entries: set[str],
    *,
    max_examples: int,
) -> tuple[int, int, int, list[dict[str, Any]]]:
    wins = losses = flats = 0
    examples: list[dict[str, Any]] = []
    for trade in audit.round_trips:
        executed_time = trade.entry_fill.execution_time.isoformat()
        if executed_time in opposite_entries:
            continue
        kind = "WIN" if trade.net_pnl > 0 else "LOSS" if trade.net_pnl < 0 else "FLAT"
        wins += int(kind == "WIN")
        losses += int(kind == "LOSS")
        flats += int(kind == "FLAT")
        if len(examples) < max_examples:
            examples.append(
                {
                    "trade_id": trade.trade_id,
                    "entry_execution_time": executed_time,
                    "observed_entry_decision_id": trade.entry_fill.decision_id,
                    "original_observed_outcome": kind,
                    "original_observed_net_pnl": trade.net_pnl,
                    "not_a_counterfactual_execution": True,
                }
            )
    return wins, losses, flats, examples


def build_costed_s7_contribution(
    parent: AcademicDecisionAudit,
    child: AcademicDecisionAudit,
    market: MarketDataSet,
    report: ControlledExperimentReport,
    hypothesis_id: str,
    *,
    max_examples: int = 8,
) -> dict[str, Any]:
    """Validate S7's *actual* costs/traces and expose whole-portfolio impact.

    The report is an already approved S7 measured object. Original canonical
    parent/child audits must be independently replayed and their S7 outcome
    cross-checked. No child score, feature causality or auto-promotion is granted.
    """
    if (
        market.zone != DataZone.DEVELOPMENT
        or type(hypothesis_id) is not str
        or not hypothesis_id
        or type(max_examples) is not int
        or not 1 <= max_examples <= 16
        or report.out_of_sample_approved is not False
        or report.broker_executable is not False
        or report.causal_status != "NOT_ESTABLISHED"
    ):
        raise ContributionEvidenceError("invalid F3 study scope")
    try:
        _checked(parent, market)
        _checked(child, market)
    except (LossAttributionError, ValueError) as exc:
        raise ContributionEvidenceError("unverified canonical decision evidence") from exc
    if (
        parent.evaluation.initial_cash != child.evaluation.initial_cash
        or parent.evaluation.strategy_hash == child.evaluation.strategy_hash
        or report.audit_hash != parent.trace_hash
        or report.dataset_hash != market.dataset_hash
        or not 1 <= len(report.experiments) <= 5
        or len({x.hypothesis_id for x in report.experiments}) != len(report.experiments)
    ):
        raise ContributionEvidenceError("S7 parent or study identity mismatch")
    outcomes = [x for x in report.experiments if x.hypothesis_id == hypothesis_id]
    if len(outcomes) != 1:
        raise ContributionEvidenceError("unknown or ambiguous S7 hypothesis")
    outcome = outcomes[0]
    base, trial = parent.evaluation, child.evaluation
    if (
        outcome.child_strategy_hash != trial.strategy_hash
        or outcome.parent_final_equity != base.final_equity
        or outcome.child_final_equity != trial.final_equity
        or outcome.parent_fill_count != base.trades_count
        or outcome.child_fill_count != trial.trades_count
        or outcome.same_fill_trace != (base.trades == trial.trades)
        or outcome.execution_delta != _execution_delta(base, trial)
        or outcome.development_windows != _development_windows(base, trial, market)
    ):
        raise ContributionEvidenceError("measured S7 outcome cannot replay")
    pm = calculate_metrics(base.equity_curve, (), periods_per_year=252.0)
    cm = calculate_metrics(trial.equity_curve, (), periods_per_year=252.0)
    p_entries = {x.execution_time.isoformat() for x in parent.fills if x.side == "buy"}
    c_entries = {x.execution_time.isoformat() for x in child.fills if x.side == "buy"}
    pwin, ploss, pflat, pexamples = _entry_cases(parent, c_entries, max_examples=max_examples)
    cwin, closs, cflat, cexamples = _entry_cases(child, p_entries, max_examples=max_examples)
    parent_exposure = _held_fraction(parent, market)
    child_exposure = _held_fraction(child, market)
    benchmark = (
        compare_qqq_development_benchmarks(market, initial_cash=base.initial_cash)[
            "qqq_costed_buy_and_hold"
        ]["total_return"]
        if all(bar.symbol == "QQQ" for bar in market.bars)
        else None
    )
    return_delta = cm.total_return - pm.total_return
    if cm.total_return < pm.total_return - 1e-12 or cm.max_drawdown > pm.max_drawdown + 1e-12:
        review = "PARENT_REMAINS_BETTER_ON_RETURN_OR_RISK"
    elif trial.trades_count == 0 or base.trades == trial.trades:
        review = "INCONCLUSIVE_DEVELOPMENT_ONLY"
    else:
        review = "CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION"
    evidence: dict[str, Any] = {
        "schema": "f3-costed-parent-child-contribution-v1",
        "hypothesis_id": hypothesis_id,
        "dataset_hash": market.dataset_hash,
        "parent_audit_hash": parent.trace_hash,
        "child_audit_hash": child.trace_hash,
        "measured_s7_report_hash": report.evidence_hash,
        "parent_strategy_hash": base.strategy_hash,
        "child_strategy_hash": trial.strategy_hash,
        "parent_equity_hash": base.equity_hash,
        "child_equity_hash": trial.equity_hash,
        "parent_final_equity": base.final_equity,
        "child_final_equity": trial.final_equity,
        "delta_final_equity": trial.final_equity - base.final_equity,
        "parent_total_return": pm.total_return,
        "child_total_return": cm.total_return,
        "return_delta": return_delta,
        "parent_max_drawdown": pm.max_drawdown,
        "child_max_drawdown": cm.max_drawdown,
        "drawdown_delta": cm.max_drawdown - pm.max_drawdown,
        "parent_sharpe": pm.sharpe,
        "child_sharpe": cm.sharpe,
        "parent_total_paid_costs": base.total_paid_costs,
        "child_total_paid_costs": trial.total_paid_costs,
        "cost_delta": trial.total_paid_costs - base.total_paid_costs,
        "parent_fill_count": base.trades_count,
        "child_fill_count": trial.trades_count,
        "parent_closed_trades": len(parent.round_trips),
        "child_closed_trades": len(child.round_trips),
        "parent_market_exposure": parent_exposure,
        "child_market_exposure": child_exposure,
        "parent_only_closed_winning_entries": pwin,
        "parent_only_closed_losing_entries": ploss,
        "parent_only_closed_flat_entries": pflat,
        "child_only_closed_winning_entries": cwin,
        "child_only_closed_losing_entries": closs,
        "child_only_closed_flat_entries": cflat,
        "parent_only_entry_examples": pexamples,
        "child_only_entry_examples": cexamples,
        "execution_delta": asdict(outcome.execution_delta),
        "development_windows": [asdict(w) for w in outcome.development_windows],
        "qqq_costed_buy_and_hold_return": benchmark,
        "parent_relative_qqq_return": (
            pm.total_return - benchmark if benchmark is not None else None
        ),
        "child_relative_qqq_return": (
            cm.total_return - benchmark if benchmark is not None else None
        ),
        "relative_qqq_return_delta": (return_delta if benchmark is not None else None),
        "adoption_review": review,
        "evaluation_required": "EXISTING_PARENT_SELECTION_AND_INDEPENDENT_OOS",
        "observed_parent_only_entries_not_proven_avoided_losses": True,
        "observed_parent_only_winners_not_proven_missed_child_profit": True,
        "not_same_entry_means_not_a_simulated_alternative_exit": True,
        "counterfactual_scope": "WHOLE_PORTFOLIO_RERUN_DESCRIPTIVE_ONLY",
        "causal_status": "NOT_ESTABLISHED",
        "independent_oos_approved": False,
        "auto_promotable": False,
        "broker_executable": False,
    }
    return {**evidence, "evidence_hash": content_hash(evidence)}


def build_verified_s7_contribution_review(
    parent_compiled: CompiledAcademicStrategy,
    child_compiled: CompiledAcademicStrategy,
    market: MarketDataSet,
    report: ControlledExperimentReport,
    hypothesis_id: str,
    *,
    weakness_guidance: dict[str, Any] | None = None,
    weakness_id: str | None = None,
) -> dict[str, Any]:
    """Independently rerun both typed IRs and link a prespecified F2 hypothesis.

    Existing audit/S7/parent selection are untouched. This is an opt-in F3
    research view; never a new S7 schema or replacement signed trade evidence.
    """
    if (
        parent_compiled.dataset_hash != market.dataset_hash
        or child_compiled.dataset_hash != market.dataset_hash
        or parent_compiled.feature_values != child_compiled.feature_values
        or parent_compiled.replay != child_compiled.replay
        or child_compiled.status != "DEVELOPMENT_ONLY"
        or parent_compiled.broker_executable is not False
        or child_compiled.broker_executable is not False
        or parent_compiled.sealed_oos_approved is not False
        or child_compiled.sealed_oos_approved is not False
    ):
        raise ContributionEvidenceError("not the same verified S7 baseline")
    from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions

    parent_audit = audit_inherited_decisions(parent_compiled, market)
    child_audit = audit_inherited_decisions(child_compiled, market)
    result = build_costed_s7_contribution(parent_audit, child_audit, market, report, hypothesis_id)
    parent_strategy, child_strategy = parent_compiled.strategy, child_compiled.strategy
    changes = [
        part
        for part in ("entry", "exit", "regime_filters", "risk", "features")
        if getattr(parent_strategy, part) != getattr(child_strategy, part)
    ]
    intervention = changes[0].upper() + "_ONLY" if len(changes) == 1 else "JOINT_OR_OTHER"
    linked: dict[str, Any] | None = None
    if weakness_guidance is not None or weakness_id is not None:
        if not isinstance(weakness_guidance, dict) or type(weakness_id) is not str:
            raise ContributionEvidenceError("missing F2 provenance reference")
        guide_hash = weakness_guidance.get("guidance_hash")
        if (
            not isinstance(guide_hash, str)
            or content_hash({k: v for k, v in weakness_guidance.items() if k != "guidance_hash"})
            != guide_hash
            or weakness_guidance.get("source_audit_hash") != parent_audit.trace_hash
            or weakness_guidance.get("strategy_hash") != parent_audit.evaluation.strategy_hash
            or weakness_guidance.get("dataset_hash") != market.dataset_hash
            or weakness_guidance.get("causal_status") != "NOT_ESTABLISHED"
        ):
            raise ContributionEvidenceError("F2 guide does not belong to S7 parent")
        matches = [
            item
            for item in weakness_guidance.get("weaknesses", [])
            if item.get("weakness_id") == weakness_id
        ]
        if len(matches) != 1:
            raise ContributionEvidenceError("unknown F2 weakness identity")
        linked = {
            "source_guidance_hash": guide_hash,
            "weakness_id": weakness_id,
            "observation_code": matches[0]["observation_code"],
            "needed_information": matches[0]["needed_information"],
            "mechanism_validation": "STILL_NOT_ESTABLISHED",
        }

    result.pop("evidence_hash")
    result["intervention_components"] = changes
    result["intervention_scope"] = intervention
    result["matched_weakness"] = linked
    return {**result, "evidence_hash": content_hash(result)}

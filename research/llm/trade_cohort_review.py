"""P2-2: Whole-cohort, development-only observational trade contrasts.

All market-state features are determined from historical bars *as of the
pre-entry decision close*. Pair matching uses realized hold duration, so it is
strictly descriptive and MUST NEVER be used as a trading rule or causal claim.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from math import isfinite
from typing import Any

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.decision_audit import AcademicDecisionAudit
from research.llm.loss_attribution import LossAttributionError, _checked, _trade_case


def _entry_regime(market: MarketDataSet, signal_index: int) -> tuple[str, str]:
    """Predeclared 20-prior-bar trend and mean absolute close return bands."""
    if signal_index < 20:
        return "WARMUP_UNKNOWN", "WARMUP_UNKNOWN"
    closes = [float(b.close) for b in market.bars[signal_index - 20 : signal_index + 1]]
    if any(not isfinite(x) or x <= 0 for x in closes):
        raise LossAttributionError("invalid historical close for regime")
    drift = closes[-1] / closes[0] - 1
    trend = "UP" if drift >= 0.03 else "DOWN" if drift <= -0.03 else "SIDEWAYS"
    daily = [abs(b / a - 1) for a, b in zip(closes[:-1], closes[1:], strict=True)]
    vol = "ELEVATED" if sum(daily) / 20 >= 0.015 else "CALM"
    return trend, vol


def _hold_band(days: int) -> str:
    return "SHORT" if days <= 5 else "MEDIUM" if days <= 20 else "LONG"


def build_trade_cohort_review(
    audit: AcademicDecisionAudit, market: MarketDataSet, *, max_pairs: int = 8
) -> dict[str, Any]:
    """Compare *all* closed wins and losses; give bounded matched examples.

    No p-value, market beta, confidence interval, causal effect, or forward
    outperformance is estimated from this selected development sample.
    """
    if type(max_pairs) is not int or not 1 <= max_pairs <= 20:
        raise LossAttributionError("invalid cohort matching budget")
    _checked(audit, market)
    if len(audit.round_trips) > 5000:
        raise LossAttributionError("unbounded closed trade cohort")
    decisions = {d.decision_id: d for d in audit.decisions}
    records: list[dict[str, Any]] = []
    for t in audit.round_trips:
        case = _trade_case(t, by_decision=decisions, market=market)
        if t.net_pnl == 0:
            outcome = "FLAT"
        else:
            outcome = "WIN" if t.net_pnl > 0 else "LOSS"
        index = decisions[t.entry_fill.decision_id].bar_index
        regime, volatility = _entry_regime(market, index)
        case.update(
            {
                "outcome": outcome,
                "entry_trend_20": regime,
                "entry_volatility_20": volatility,
                "hold_band": _hold_band(case["held_bars"]),
            }
        )
        records.append(case)
    grouped: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    count_by_code: dict[str, Counter[str]] = defaultdict(Counter)
    for case in records:
        grouped[(case["entry_trend_20"], case["entry_volatility_20"], case["hold_band"])][
            case["outcome"]
        ] += 1
        for code in case["observation_codes"]:
            count_by_code[code][case["outcome"]] += 1
    cases_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for case in records:
        if case["outcome"] == "WIN":
            cases_by_key[
                (case["entry_trend_20"], case["entry_volatility_20"], case["hold_band"])
            ].append(case)
    used: set[str] = set()
    pairs: list[dict[str, Any]] = []
    lost = sorted(
        (r for r in records if r["outcome"] == "LOSS"), key=lambda r: (r["net_pnl"], r["trade_id"])
    )
    for loss in lost:
        key = (loss["entry_trend_20"], loss["entry_volatility_20"], loss["hold_band"])
        eligible = [p for p in cases_by_key[key] if p["trade_id"] not in used]
        if not eligible:
            continue
        matched = min(
            eligible, key=lambda p: (abs(p["held_bars"] - loss["held_bars"]), p["trade_id"])
        )
        used.add(matched["trade_id"])
        pairs.append(
            {
                "loss_trade_id": loss["trade_id"],
                "win_trade_id": matched["trade_id"],
                "entry_regime": key[0],
                "entry_volatility": key[1],
                "hold_band": key[2],
                "loss_pnl": loss["net_pnl"],
                "win_pnl": matched["net_pnl"],
                "holding_bar_gap": abs(matched["held_bars"] - loss["held_bars"]),
                "shared_observations": sorted(
                    set(loss["observation_codes"]) & set(matched["observation_codes"])
                ),
                "loss_only_observations": sorted(
                    set(loss["observation_codes"]) - set(matched["observation_codes"])
                ),
                "win_only_observations": sorted(
                    set(matched["observation_codes"]) - set(loss["observation_codes"])
                ),
                "not_causal_matching": True,
            }
        )
    # All possible non-reused matches are counted. Only *display* is bounded;
    # do not conflate unmatched cases with undisplayed matched cases.
    matched_pairs_total = len(pairs)
    pairs = pairs[:max_pairs]
    outcome_counts = Counter(row["outcome"] for row in records)
    cohorts = [
        {
            "entry_trend_20": key[0],
            "entry_volatility_20": key[1],
            "hold_band": key[2],
            "wins": stats["WIN"],
            "losses": stats["LOSS"],
            "flats": stats["FLAT"],
            "insufficient_for_inference": (stats["WIN"] < 5 or stats["LOSS"] < 5),
        }
        for key, stats in sorted(grouped.items())
    ]
    codes = []
    for code, stats in sorted(count_by_code.items()):
        n_loss, n_win = outcome_counts["LOSS"], outcome_counts["WIN"]
        loss_fraction = stats["LOSS"] / n_loss if n_loss else None
        win_fraction = stats["WIN"] / n_win if n_win else None
        codes.append(
            {
                "code": code,
                "losing_trades_with_code": stats["LOSS"],
                "winning_trades_with_code": stats["WIN"],
                "all_loss_count": n_loss,
                "all_win_count": n_win,
                "loss_fraction": loss_fraction,
                "win_fraction": win_fraction,
                "descriptive_rate_gap": (
                    loss_fraction - win_fraction
                    if loss_fraction is not None and win_fraction is not None
                    else None
                ),
                "not_proven_predictive": True,
            }
        )
    body: dict[str, Any] = {
        "schema": "full-development-trade-cohort-review-p2-2-v1",
        "source_audit_hash": audit.trace_hash,
        "strategy_hash": audit.evaluation.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "closed_trades": len(records),
        "wins": outcome_counts["WIN"],
        "losses": outcome_counts["LOSS"],
        "flats": outcome_counts["FLAT"],
        "entry_regime_definition": (
            "20 prior closed bars; close drift +/-3%; mean abs daily change >=1.5%"
        ),
        "regime_asof": "PRE_ENTRY_SIGNAL_BAR_CLOSE_ONLY",
        "cohorts": cohorts,
        "indicator_observation_frequencies": codes,
        "matched_example_pairs": pairs,
        "matched_pair_count": len(pairs),
        "matched_pairs_total": matched_pairs_total,
        "undisplayed_matched_pairs": matched_pairs_total - len(pairs),
        "unmatched_loss_count": len(lost) - matched_pairs_total,
        "selection_notice": (
            "Outcome/holding period hindsight; not randomized, propensity matched, or forward test"
        ),
        "statistical_significance": "NOT_ESTABLISHED",
        "causal_status": "NOT_ESTABLISHED",
        "validation_scope": "REUSED_DEVELOPMENT_ONLY",
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    return {**body, "evidence_hash": content_hash(body)}


def link_completed_s7_to_cohort(
    audit: AcademicDecisionAudit,
    ancestor: Mapping[str, Any],
    stored: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Attach the latest already measured S7 to its original trade observations.

    It proves what changed for this *hypothesis*, not that its narrative
    explains the improvement, nor that it generalizes outside development.
    """
    body: dict[str, Any] = {
        "schema": "cohort-s7-linked-evidence-p2-2-v1",
        "source_generation": ancestor["generation"],
        "source_generation_evidence_hash": ancestor["evidence_hash"],
        "source_audit_hash": audit.trace_hash,
        "status": "NO_MEASURED_S7_FOR_GENERATION"
        if stored is None
        else "MEASURED_S7_REUSED_DEVELOPMENT",
        "linked_experiments": [],
        "no_causal_inference": True,
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    if (
        ancestor.get("audit_hash") != audit.trace_hash
        or ancestor.get("strategy_hash") != audit.evaluation.strategy_hash
    ):
        raise LossAttributionError("S7 ancestor audit/strategy identity mismatch")
    if stored is None:
        return {**body, "evidence_hash": content_hash(body)}
    report_hash = stored.get("record_hash")
    if (
        not isinstance(report_hash, str)
        or content_hash({k: v for k, v in stored.items() if k != "record_hash"}) != report_hash
        or stored.get("original_generation_evidence_hash") != ancestor["evidence_hash"]
        or stored.get("generation") != ancestor["generation"]
        or stored.get("study_scope") != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
    ):
        raise LossAttributionError("S7 linked report hash or ancestry mismatch")
    report = stored["report"]
    if (
        report.get("causal_status") != "NOT_ESTABLISHED"
        or report.get("out_of_sample_approved") is not False
        or report.get("broker_executable") is not False
        or report.get("dataset_hash") != audit.evaluation.dataset_hash
        or report.get("audit_hash") != audit.trace_hash
    ):
        raise LossAttributionError("S7 linked validation scope mismatch")
    proposals = ancestor.get("experiments")
    measured = report.get("experiments")
    if (
        not isinstance(proposals, list)
        or not isinstance(measured, list)
        or len(proposals) != len(measured)
    ):
        raise LossAttributionError("S7 linked hypothesis count mismatch")
    relevant_ids = (
        {d.decision_id for d in audit.decisions}
        | {f.fill_id for f in audit.fills}
        | {t.trade_id for t in audit.round_trips}
        | {f.trade_id for f in audit.fills}
    )
    proposal_by_id = {p["hypothesis_id"]: p for p in proposals}
    if len(proposal_by_id) != len(proposals):
        raise LossAttributionError("S7 duplicate original proposal")
    for trial in measured:
        hypothesis_id = trial.get("hypothesis_id")
        p = proposal_by_id.get(hypothesis_id)
        if p is None or any(ref not in relevant_ids for ref in p["observed_ids"]):
            raise LossAttributionError("S7 proposed hypothesis not grounded in real decision IDs")
        if (
            trial.get("child_strategy_hash") != p.get("proposal_child_hash")
            or trial.get("causal_status") != "NOT_ESTABLISHED"
            or trial.get("expected_direction") != p.get("predicted_direction")
            or trial.get("metric") != p.get("expected_metric")
            or abs(float(trial["parent_final_equity"]) - audit.evaluation.final_equity) > 1e-6
        ):
            raise LossAttributionError("S7 paired trial/parent identity mismatch")
        child_equity = float(trial["child_final_equity"])
        if not isfinite(child_equity) or child_equity < 0:
            raise LossAttributionError("S7 invalid child final equity")
        costs = trial.get("execution_delta") or {}
        if any(
            type(costs.get(k)) not in (int, float) or not isfinite(costs[k]) or costs[k] < 0
            for k in ("parent_costs", "child_costs")
        ):
            raise LossAttributionError("S7 missing economic costs")
        delta = child_equity - audit.evaluation.final_equity
        body["linked_experiments"].append(
            {
                "hypothesis_id": hypothesis_id,
                "observed_ids": p["observed_ids"],
                "original_mechanism": p["mechanism"],
                "alternative_explanation": p["alternative"],
                "test_design": p["test_design"],
                "changed_strategy_hash": trial["child_strategy_hash"],
                "predicted_direction_status": trial["status"],
                "tested_metric": trial["metric"],
                "parent_final_equity": audit.evaluation.final_equity,
                "child_final_equity": child_equity,
                "net_equity_delta": delta,
                "economic_direction": "BETTER"
                if delta > 1e-6
                else "WORSE"
                if delta < -1e-6
                else "SAME",
                "parent_costs": costs["parent_costs"],
                "child_costs": costs["child_costs"],
                "result_scope": "MEASURED_REUSED_DEVELOPMENT_NOT_ALPHA",
                "causal_status": "NOT_ESTABLISHED",
            }
        )
    body["source_s7_report_hash"] = report_hash
    return {**body, "evidence_hash": content_hash(body)}

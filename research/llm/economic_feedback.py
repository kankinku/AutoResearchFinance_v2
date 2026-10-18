"""P0: evidence-bound economic results of S7 experiments, advisory only.

A direction match for trade_count is NOT a profitable result. Never train a
model, select an executable strategy, or claim OOS validation from this module.
Immutable generation/experiment evidence is only read and verified.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from core.integrity.hashes import content_hash


class EconomicFeedbackError(ValueError):
    """Unreliable provenance or numeric fields in paired research evidence."""


_SCOPE = "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
_DIRECTION = {
    "RETURN_BETTER_DEVELOPMENT",
    "RETURN_WORSE_DEVELOPMENT",
    "RETURN_UNCHANGED_DEVELOPMENT",
}


def _finite(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise EconomicFeedbackError(f"invalid finite {name}")
    return float(value)


def build_economic_feedback(
    history: Sequence[Mapping[str, Any]],
    records: Mapping[int, Mapping[str, Any]],
    *,
    max_candidates: int = 5,
    min_closed_trades: int = 30,
    qqq_total_return: float | None = None,
) -> dict[str, Any]:
    """Expose verified paired net outcomes and bounded *review-only* children.

    The historical trade-cost model is shared by parent and child; other risk
    dimensions are *not* certified. Four retrospective development windows
    must never be described as out-of-sample or prospective confirmation.
    """
    if (
        len(history) > 100
        or len(records) > len(history)
        or not 1 <= max_candidates <= 10
        or not 1 <= min_closed_trades <= 1000
    ):
        raise EconomicFeedbackError("invalid research bounds")
    benchmark = (
        None
        if qqq_total_return is None
        else _finite(qqq_total_return, "QQQ development total return")
    )
    if benchmark is not None and benchmark <= -1:
        raise EconomicFeedbackError("invalid QQQ benchmark total return")
    tested: Counter[str] = Counter()
    execution_counts: Counter[str] = Counter()
    category_outcomes: dict[str, Counter[str]] = {
        name: Counter()
        for name in ("SIGNAL_TIMING_CHANGED", "SIZE_ONLY_CHANGED", "UNCHANGED_EXECUTIONS")
    }
    size_reviews: list[dict[str, Any]] = []
    outcomes: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    latest: dict[str, Any] | None = None
    total = 0
    for generation, row in sorted(records.items()):
        if type(generation) is not int or generation < 1 or generation > len(history):
            raise EconomicFeedbackError("orphan paired experiment generation")
        ancestor = history[generation - 1]
        if (
            type(ancestor.get("generation")) is not int
            or ancestor["generation"] != generation
            or row.get("original_generation_evidence_hash") != ancestor.get("evidence_hash")
        ):
            raise EconomicFeedbackError("original generation evidence mismatch")
        record_hash = row.get("record_hash")
        if not isinstance(record_hash, str) or len(record_hash) != 64:
            raise EconomicFeedbackError("missing record integrity hash")
        if content_hash({k: v for k, v in row.items() if k != "record_hash"}) != record_hash:
            raise EconomicFeedbackError("controlled report integrity mismatch")
        report = row.get("report")
        if (
            row.get("study_scope") != _SCOPE
            or not isinstance(report, dict)
            or report.get("causal_status") != "NOT_ESTABLISHED"
            or report.get("out_of_sample_approved") is not False
            or report.get("broker_executable") is not False
            or report.get("diagnostic_proposal_hash") != ancestor.get("diagnostic_proposal_hash")
        ):
            raise EconomicFeedbackError("controlled report provenance mismatch")
        experiments = report.get("experiments")
        proposals = ancestor.get("experiments")
        if not isinstance(experiments, (tuple, list)) or not isinstance(proposals, list):
            raise EconomicFeedbackError("invalid experiment list")
        expected = {p.get("hypothesis_id"): p for p in proposals if isinstance(p, dict)}
        if len(expected) != len(proposals) or len(experiments) != len(proposals):
            raise EconomicFeedbackError("mismatched hypothesis count")
        metrics = ancestor.get("metrics")
        if not isinstance(metrics, dict):
            raise EconomicFeedbackError("missing parent metrics")
        parent_return = _finite(metrics.get("total_return"), "parent total return")
        parent_final = _finite(ancestor.get("measured_final_equity"), "parent final equity")
        if parent_return <= -1 or parent_final <= 0:
            raise EconomicFeedbackError("invalid parent equity scale")
        cash = parent_final / (1 + parent_return)
        if not math.isfinite(cash) or cash <= 0:
            raise EconomicFeedbackError("invalid parent initial capital")
        seen: set[str] = set()
        for trial in experiments:
            if not isinstance(trial, dict):
                raise EconomicFeedbackError("unstructured experiment")
            hid = trial.get("hypothesis_id")
            if not isinstance(hid, str) or hid not in expected or hid in seen:
                raise EconomicFeedbackError("unknown or repeated hypothesis")
            seen.add(hid)
            proposal = expected[hid]
            if (
                trial.get("child_strategy_hash") != proposal.get("proposal_child_hash")
                or trial.get("causal_status") != "NOT_ESTABLISHED"
            ):
                raise EconomicFeedbackError("child strategy hash or causal status mismatch")
            baseline = _finite(trial.get("parent_final_equity"), "parent equity")
            child = _finite(trial.get("child_final_equity"), "child equity")
            if not math.isclose(baseline, parent_final, rel_tol=1e-7, abs_tol=0.0001):
                raise EconomicFeedbackError("parent equity differs from audited generation")
            if child < 0:
                raise EconomicFeedbackError("negative child equity")
            before, after = trial.get("parent_fill_count"), trial.get("child_fill_count")
            if type(before) is not int or type(after) is not int or before < 0 or after < 0:
                raise EconomicFeedbackError("invalid fill counts")
            windows = trial.get("development_windows")
            if not isinstance(windows, (tuple, list)) or len(windows) != 4:
                raise EconomicFeedbackError("missing four descriptive development windows")
            worse_windows = 0
            better_return_windows = 0
            worse_return_windows = 0
            lower_drawdown_windows = 0
            for win in windows:
                if not isinstance(win, dict):
                    raise EconomicFeedbackError("malformed retrospective window")
                parent_dd = _finite(win.get("parent_max_drawdown"), "window parent drawdown")
                child_dd = _finite(win.get("child_max_drawdown"), "window child drawdown")
                if not (0 <= parent_dd <= 1 and 0 <= child_dd <= 1):
                    raise EconomicFeedbackError("out-of-bounds retrospective drawdown")
                if child_dd > parent_dd + 1e-12:
                    worse_windows += 1
                elif child_dd < parent_dd - 1e-12:
                    lower_drawdown_windows += 1
                parent_win_return = _finite(win.get("parent_total_return"), "parent window return")
                child_win_return = _finite(win.get("child_total_return"), "child window return")
                if child_win_return > parent_win_return + 1e-12:
                    better_return_windows += 1
                elif child_win_return < parent_win_return - 1e-12:
                    worse_return_windows += 1
            observed_change = trial.get("execution_delta")
            if not isinstance(observed_change, dict):
                raise EconomicFeedbackError("missing measured execution delta")
            event_counts: dict[str, int] = {}
            for key in ("added_event_count", "removed_event_count", "resized_event_count"):
                n = observed_change.get(key)
                if type(n) is not int or n < 0:
                    raise EconomicFeedbackError("invalid execution change count")
                event_counts[key] = n
            timing = observed_change.get("execution_timing_changed", False)
            if type(timing) is not bool:
                raise EconomicFeedbackError("invalid execution timing change")
            if event_counts["added_event_count"] or event_counts["removed_event_count"] or timing:
                execution_kind = "SIGNAL_TIMING_CHANGED"
            elif event_counts["resized_event_count"]:
                execution_kind = "SIZE_ONLY_CHANGED"
            else:
                execution_kind = "UNCHANGED_EXECUTIONS"
            execution_counts[execution_kind] += 1
            parent_cost = observed_change.get("parent_costs")
            child_cost = observed_change.get("child_costs")
            # Legacy synthetic S7 tests do not carry audited cost attribution.
            costs_verified = parent_cost is not None and child_cost is not None
            if costs_verified:
                parent_cost = _finite(parent_cost, "parent measured transaction costs")
                child_cost = _finite(child_cost, "child measured transaction costs")
                if parent_cost < 0 or child_cost < 0:
                    raise EconomicFeedbackError("negative transaction costs")
            improvement_pp = 100 * (child - baseline) / cash
            if math.isclose(child, baseline, abs_tol=1e-8, rel_tol=1e-12):
                direction = "RETURN_UNCHANGED_DEVELOPMENT"
                outcomes["return_unchanged"] += 1
            elif child > baseline:
                direction = "RETURN_BETTER_DEVELOPMENT"
                outcomes["return_better"] += 1
            else:
                direction = "RETURN_WORSE_DEVELOPMENT"
                outcomes["return_worse"] += 1
            assert direction in _DIRECTION
            category_outcomes[execution_kind][direction] += 1
            metric = trial.get("metric")
            if not isinstance(metric, str):
                raise EconomicFeedbackError("invalid controlled metric name")
            tested[metric] += 1
            total += 1
            approx_closed = after // 2
            latest = {
                "generation": generation,
                "hypothesis_id": hid,
                "tested_metric": metric,
                "economic_direction": direction,
                "return_delta_pp": round(improvement_pp, 8),
                "parent_total_return_pct": round(parent_return * 100, 8),
                "child_total_return_pct": round(100 * (child / cash - 1), 8),
                "child_closed_trades_estimate": approx_closed,
                "child_fill_count": after,
                "worse_drawdown_development_windows": worse_windows,
                "lower_drawdown_development_windows": lower_drawdown_windows,
                "better_return_development_windows": better_return_windows,
                "worse_return_development_windows": worse_return_windows,
                "execution_change_kind": execution_kind,
                "actual_signal_timing_change": execution_kind == "SIGNAL_TIMING_CHANGED",
                "resized_event_count": event_counts["resized_event_count"],
                "added_event_count": event_counts["added_event_count"],
                "removed_event_count": event_counts["removed_event_count"],
                "parent_transaction_costs": parent_cost if costs_verified else None,
                "child_transaction_costs": child_cost if costs_verified else None,
                "transaction_costs_individually_verified": costs_verified,
                "child_exposure_verified": False,
                "child_max_drawdown_full_period_verified": metric == "max_drawdown",
                "parent_full_period_mdd": (
                    _finite(trial.get("parent_metric"), "parent full period MDD")
                    if metric == "max_drawdown"
                    else None
                ),
                "child_full_period_mdd": (
                    _finite(trial.get("child_metric"), "child full period MDD")
                    if metric == "max_drawdown"
                    else None
                ),
                "qqq_costed_buy_hold_total_return_pct": (
                    round(100 * benchmark, 8) if benchmark is not None else None
                ),
                "child_minus_qqq_total_return_pp": (
                    round(100 * (child / cash - 1 - benchmark), 8)
                    if benchmark is not None
                    else None
                ),
                "parent_evidence_hash": ancestor["evidence_hash"],
                "controlled_record_hash": record_hash,
            }
            if direction == "RETURN_BETTER_DEVELOPMENT" and approx_closed >= min_closed_trades:
                review = {
                    **latest,
                    "child_strategy_hash": trial["child_strategy_hash"],
                    "proposed_intent": deepcopy(proposal.get("proposed_intent")),
                    "causal_status": "NOT_ESTABLISHED",
                    "decision": "MANUAL_REPLAY_AND_INDEPENDENT_REVIEW_ONLY",
                }
                if execution_kind == "SIGNAL_TIMING_CHANGED":
                    candidates.append(review)
                elif execution_kind == "SIZE_ONLY_CHANGED":
                    size_reviews.append(
                        {
                            "generation": generation,
                            "hypothesis_id": hid,
                            "return_delta_pp": latest["return_delta_pp"],
                            "parent_full_period_mdd": latest["parent_full_period_mdd"],
                            "child_full_period_mdd": latest["child_full_period_mdd"],
                            "economic_direction": direction,
                            "execution_change_kind": execution_kind,
                            "child_minus_qqq_total_return_pp": latest[
                                "child_minus_qqq_total_return_pp"
                            ],
                            "decision": "MECHANICAL_SIZE_RISK_REVIEW_ONLY_NO_SIGNAL_IMPROVEMENT",
                            "controlled_record_hash": record_hash,
                        }
                    )
    # Sorting is a compact development review queue, NOT a model optimizer.
    # Show both improvement and validation limits; never execute a child.
    candidates.sort(
        key=lambda z: (
            -z["return_delta_pp"],
            z["worse_drawdown_development_windows"],
            z["generation"],
            z["hypothesis_id"],
        )
    )
    size_reviews.sort(key=lambda x: (-x["return_delta_pp"], x["generation"], x["hypothesis_id"]))
    return {
        "schema": "p0-paired-development-economic-feedback-v1",
        "status": "REUSED_DEVELOPMENT_NOT_INDEPENDENT_VALIDATION",
        "completed_generations": len(history),
        "tested_experiments": total,
        "tested_metric_counts": dict(sorted(tested.items())),
        "outcomes": {k: outcomes[k] for k in ("return_better", "return_worse", "return_unchanged")},
        "latest": latest,
        "review_candidates": candidates[:max_candidates],
        "signal_review_candidates": [
            {
                "generation": x["generation"],
                "hypothesis_id": x["hypothesis_id"],
                "return_delta_pp": x["return_delta_pp"],
                "child_minus_qqq_total_return_pp": x["child_minus_qqq_total_return_pp"],
                "worse_drawdown_development_windows": x["worse_drawdown_development_windows"],
                "actual_signal_timing_change": True,
                "controlled_record_hash": x["controlled_record_hash"],
            }
            for x in candidates[:max_candidates]
        ],
        "mechanical_size_risk_reviews": size_reviews[:max_candidates],
        "execution_change_counts": dict(sorted(execution_counts.items())),
        "economic_outcomes_by_execution_type": {
            key: dict(sorted(value.items())) for key, value in sorted(category_outcomes.items())
        },
        "signal_effect_gate": "REQUIRES_ADDED_REMOVED_OR_TIMING_CHANGED_FILLS",
        "exposure_comparison": "CHILD_EXPOSURE_UNAVAILABLE_REPLAY_REQUIRED",
        "qqq_benchmark_scope": (
            "COSTED_RAW_QQQ_SAME_REUSED_DEVELOPMENT_ONLY"
            if benchmark is not None
            else "NO_VERIFIED_QQQ_BENCHMARK_SUPPLIED"
        ),
        "research_objective": {
            "primary_metric": "total_return",
            "primary_metrics": ["total_return", "cagr", "sharpe", "max_drawdown"],
            "required_tradeoffs": [
                "transaction_costs",
                "market_exposure",
                "drawdown",
                "number_of_trades",
                "qqq_buy_hold",
            ],
            "trade_count_is_not_success": True,
            "min_closed_trades_for_review": min_closed_trades,
        },
        "automatic_child_promotion": False,
        "independent_oos_approved": False,
        "real_trading_enabled": False,
        "causal_status": "NOT_ESTABLISHED",
        "history_evidence_hash": content_hash(
            {
                "generation_hashes": [item.get("evidence_hash") for item in history],
                "report_hashes": [records[k].get("record_hash") for k in sorted(records)],
            }
        ),
    }


def gate_research_direction(
    direction: Mapping[str, Any],
    feedback: Mapping[str, Any],
) -> dict[str, Any]:
    """Prevent trade-count direction matches from being labelled EVOLVE
    when paired economic returns worsened or the child became inactive.
    """
    result = dict(direction)
    latest = feedback.get("latest")
    if (
        result.get("recommended_mode") != "EVOLVE"
        or not isinstance(latest, dict)
        or latest.get("generation") != result.get("completed_generations")
    ):
        return result
    if latest.get("execution_change_kind") == "SIZE_ONLY_CHANGED":
        result["recommended_mode"] = "TEST_HYPOTHESIS"
        result["reason_code"] = "LATEST_MECHANICAL_SIZING_NOT_SIGNAL_EVOLUTION"
    elif latest.get("execution_change_kind") == "UNCHANGED_EXECUTIONS":
        result["recommended_mode"] = "EXPLORE"
        result["reason_code"] = "LATEST_CONTROL_NO_SIGNAL_OR_SIZE_CHANGE"
    elif latest.get("child_fill_count") == 0:
        result["recommended_mode"] = "EXPLORE"
        result["reason_code"] = "LATEST_CONTROL_INACTIVE_CHILD"
    elif latest.get("economic_direction") == "RETURN_WORSE_DEVELOPMENT":
        result["recommended_mode"] = "TEST_HYPOTHESIS"
        result["reason_code"] = "LATEST_MATCHED_CONTROL_LOWER_DEVELOPMENT_RETURN"
    elif latest.get("economic_direction") == "RETURN_UNCHANGED_DEVELOPMENT":
        result["recommended_mode"] = "EXPLORE"
        result["reason_code"] = "LATEST_MATCHED_CONTROL_NO_ECONOMIC_EFFECT"
    elif latest.get("child_closed_trades_estimate", 0) < feedback.get("research_objective", {}).get(
        "min_closed_trades_for_review", 30
    ):
        result["recommended_mode"] = "TEST_HYPOTHESIS"
        result["reason_code"] = "LATEST_CONTROL_INSUFFICIENT_TRADES"
    result["economics_gate"] = "DEVELOPMENT_ONLY_NOT_PROVEN_ALPHA"
    return result

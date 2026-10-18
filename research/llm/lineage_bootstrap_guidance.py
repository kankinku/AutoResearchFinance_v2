"""Bounded, read-only hints for bootstrapping existing S7 lineage.

This does NOT promote candidates. A GPT must propose a real continuation intent;
existing verified_child_successor / lineage_selection / inherited S2 gates own
all replay, trading evidence, economics and promotion decisions.
"""

from __future__ import annotations

from math import isfinite
from typing import Any


class LineageBootstrapIntegrityError(ValueError):
    """An S7 row does not match the frozen cycle proposal/evidence."""


def _amount(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        return None
    return float(value)


def build_lineage_bootstrap_guidance(
    history: list[dict[str, Any]],
    measured_reports: dict[int, dict[str, Any]],
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """Find *replay-worthy* ordinary-plan S7 children, not verified parents.

    Filter mechanistic risk resizing: added/removed/timing-changed executions are
    required. The existing authoritative lineage replay must still establish
    exact fills, >=30 CLOSED trades and positive successor economics.
    """
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("bootstrap hint display limit must be 1..10")
    hints: list[dict[str, Any]] = []
    measured_count = 0
    for source in history:
        if source.get("inherited_strategy_ir") is not None:
            continue  # Counted-child selection already handles inherited S7.
        gen = source.get("generation")
        if type(gen) is not int or not 1 <= gen <= 100:
            raise LineageBootstrapIntegrityError("invalid source generation")
        stored = measured_reports.get(gen)
        if stored is None:
            continue
        measured_count += 1
        report = stored.get("report")
        if not isinstance(report, dict) or (
            stored.get("original_generation_evidence_hash") != source.get("evidence_hash")
            or report.get("audit_hash") != source.get("audit_hash")
            or report.get("diagnostic_proposal_hash") != source.get("diagnostic_proposal_hash")
            or report.get("dataset_hash") != source.get("dataset_hash")
        ):
            raise LineageBootstrapIntegrityError("S7 bootstrap source evidence mismatch")
        measured = report.get("experiments")
        proposals = source.get("experiments")
        if not isinstance(measured, list) or not isinstance(proposals, list):
            raise LineageBootstrapIntegrityError("S7 experiment proposal list missing")
        by_id = {item.get("hypothesis_id"): item for item in proposals}
        if len(by_id) != len(proposals):
            raise LineageBootstrapIntegrityError("duplicate source hypothesis identity")
        for trial in measured:
            hypothesis = trial.get("hypothesis_id")
            proposal = by_id.get(hypothesis)
            if proposal is None or (
                trial.get("child_strategy_hash") != proposal.get("proposal_child_hash")
                or trial.get("causal_status") != "NOT_ESTABLISHED"
            ):
                raise LineageBootstrapIntegrityError("S7 child identity mismatch")
            delta = trial.get("execution_delta")
            if not isinstance(delta, dict):
                continue
            added, removed = (
                _amount(delta.get("added_event_count")),
                _amount(delta.get("removed_event_count")),
            )
            parent, child = (
                _amount(trial.get("parent_final_equity")),
                _amount(trial.get("child_final_equity")),
            )
            fill_count = trial.get("child_fill_count")
            if (
                added is None
                or removed is None
                or added < 0
                or removed < 0
                or parent is None
                or child is None
                or child <= parent
                or type(fill_count) is not int
                or fill_count < 60
                or not (added + removed > 0 or delta.get("execution_timing_changed") is True)
            ):
                continue
            original_plan = source.get("algorithm_plan")
            if not isinstance(original_plan, dict) or not isinstance(
                original_plan.get("plan_id"), str
            ):
                raise LineageBootstrapIntegrityError("source plan identity unavailable")
            hints.append(
                {
                    "source_generation": gen,
                    "source_evidence_hash": source["evidence_hash"],
                    "s7_report_hash": stored["record_hash"],
                    "hypothesis_id": hypothesis,
                    "child_strategy_hash": trial["child_strategy_hash"],
                    "continuation_parent_strategy_id": original_plan["plan_id"],
                    "observed_equity_gain": child - parent,
                    "child_fill_events": fill_count,
                    "changed_event_count": int(added + removed),
                    "status": "REPLAY_REQUIRED_NOT_PROMOTED",
                }
            )
    hints.sort(key=lambda item: (-item["observed_equity_gain"], item["source_generation"]))
    return {
        "schema": "research-lineage-bootstrap-guidance-v1",
        "status": "REPLAY_CANDIDATES_FOUND" if hints else "NO_SIGNAL_IMPROVING_CHILD_FOUND",
        "reviewed_s7_generations": measured_count,
        "possible_candidates": len(hints),
        "candidates": hints[:limit],
        "required_action": (
            "Submit an independently reasoned continuation_intent for a proposed child "
            "using existing evaluate_algorithm_experiments continuation mode, with its "
            "exact checkpoint_token. The existing child->successor replay and parent "
            "selection must verify fills, >=30 closed trades, economics and hashes. "
            "These hints are NOT verified successors or independent OOS evidence."
            if hints
            else "No eligible measured child hints; continue original exploratory research "
            "or seek a separately verified lineage. Do not invent a parent."
        ),
        "automatic_parent_promotion": False,
        "orders_enabled": False,
        "independent_oos_approved": False,
    }

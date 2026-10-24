"""P4-3 opt-in precommit vetting of actual canonical controlled S7 experiments.

Strictly research-only: wrong-direction experiments remain valuable falsifying
observations, but identical execution, inactive children and unavailable metrics
must be corrected at the SAME diagnosis checkpoint before consuming a generation.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.integrity.hashes import content_hash
from research.indicator_engine.controlled_experiments import ControlledExperimentReport


class P4S7Rejected(ValueError):
    def __init__(self, reasons: tuple[dict[str, Any], ...]):
        self.reasons = reasons
        super().__init__(
            "P4_S7_QUALITY_REJECTED: "
            + ", ".join(f"{x['hypothesis_id']}={x['reason']}" for x in reasons)
            + "; revise the S7 hypothesis using the SAME checkpoint token"
        )


def assess_p4_s7_quality(report: ControlledExperimentReport) -> dict[str, Any]:
    """Only definite no-effect/degenerate/unmeasurable trials block the commit."""
    rejected: list[dict[str, Any]] = []
    for trial in report.experiments:
        reason = trial.status
        if reason in {"NO_OBSERVED_EFFECT", "DEGENERATE_INACTIVE_CHILD", "METRIC_UNAVAILABLE"}:
            rejected.append({
                "hypothesis_id": trial.hypothesis_id,
                "reason": reason,
                "parent_fill_count": trial.parent_fill_count,
                "child_fill_count": trial.child_fill_count,
                "same_fill_trace": trial.same_fill_trace,
                "measured_delta": trial.delta,
                "guidance": {
                    "NO_OBSERVED_EFFECT": (
                        "Canonical fills/equity unchanged. Alter a signal threshold, "
                        "entry/exit logic or test a distinct causal intervention."
                    ),
                    "DEGENERATE_INACTIVE_CHILD": (
                        "The proposed child eliminated all executions. "
                        "Revise to preserve measurable participation."
                    ),
                    "METRIC_UNAVAILABLE": (
                        "The selected metric is undefined on this run. "
                        "Choose another supported measurable metric."
                    ),
                }[reason],
            })
    if rejected:
        raise P4S7Rejected(tuple(rejected))
    body = {
        "schema": "p4-s7-precommit-quality-v1",
        "study_scope": "REUSED_DEVELOPMENT_EX_POST_NOT_OOS",
        "evidence_hash": report.evidence_hash,
        "eligible": True,
        "hypothesis_statuses": [
            {"hypothesis_id": x.hypothesis_id, "status": x.status,
             "execution_delta": asdict(x.execution_delta)}
            for x in report.experiments
        ],
        "broker_executable": False,
        "independent_oos_approved": False,
    }
    return {**body, "review_hash": content_hash(body)}

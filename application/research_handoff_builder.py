"""M0: derive evidence-linked research events from existing Quant MCP checkpoints.

Research data, not instructions. Neither immutable journal nor model parameters
are edited. This stage deliberately makes no claim of token-optimal summarizing,
provider-attested GPT generations, alpha, or independent OOS approval.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from core.integrity.hashes import content_hash
from research.llm.autonomous_cycle import AcademicCycleService
from research.llm.experiment_learning import (
    ExperimentLearningError,
    build_experiment_learning,
)


class ResearchHandoffError(ValueError):
    """Refuse to summarize a missing or invalid canonical evidence chain."""


_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SID = re.compile(r"[0-9a-f]{32}\Z")
_ALLOWED_PHASES = {"AWAITING_PLAN", "AWAITING_DIAGNOSIS", "COMPLETED"}


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _check_snapshot(snapshot: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    sid = snapshot.get("session_id")
    if not isinstance(sid, str) or _SID.fullmatch(sid) is None:
        raise ResearchHandoffError("invalid session ID")
    if (
        snapshot.get("orders_enabled") is not False
        or snapshot.get("independent_oos_approved") is not False
    ):
        raise ResearchHandoffError("non-trading development scope required")
    if not _valid_hash(snapshot.get("dataset_hash")):
        raise ResearchHandoffError("invalid dataset identity")
    if not isinstance(snapshot.get("catalog_version"), str) or not snapshot["catalog_version"]:
        raise ResearchHandoffError("missing academic catalog version")
    phase = snapshot.get("checkpoint_phase")
    done = snapshot.get("completed_generations")
    target = snapshot.get("requested_generations")
    if (
        phase not in _ALLOWED_PHASES
        or type(done) is not int
        or type(target) is not int
        or not 0 <= done <= target <= 1000
    ):
        raise ResearchHandoffError("invalid canonical generation state")
    if (phase == "COMPLETED") != (done == target):
        raise ResearchHandoffError("completed phase/count mismatch")
    if (phase == "COMPLETED") != (snapshot.get("status") == "COMPLETED"):
        raise ResearchHandoffError("session status is inconsistent")
    history = snapshot.get("history")
    if not isinstance(history, list) or len(history) != done:
        raise ResearchHandoffError("missing canonical generation history")
    prev: str | None = None
    for n, row in enumerate(history, 1):
        if not isinstance(row, dict) or row.get("generation") != n:
            raise ResearchHandoffError("invalid canonical generation sequence")
        evidence_hash = row.get("evidence_hash")
        if not _valid_hash(evidence_hash) or row.get("previous_evidence_hash") != prev:
            raise ResearchHandoffError("canonical chain parent mismatch")
        payload = {k: v for k, v in row.items() if k != "evidence_hash"}
        if AcademicCycleService._row_evidence_hash(sid, n, prev, payload) != evidence_hash:
            raise ResearchHandoffError("canonical generation evidence hash mismatch")
        if row.get("dataset_hash") != snapshot["dataset_hash"]:
            raise ResearchHandoffError("canonical generation dataset mismatch")
        prev = evidence_hash
    return sid, history


def _check_receipts(
    sid: str,
    history: list[dict[str, Any]],
    s7_receipts: Mapping[int, Mapping[str, Any]],
) -> None:
    if set(s7_receipts) != set(range(1, len(history) + 1)) or any(
        type(key) is not int for key in s7_receipts
    ):
        raise ResearchHandoffError("missing or extraneous committed S7 generation")
    for n, row in enumerate(history, 1):
        receipt = s7_receipts[n]
        if not isinstance(receipt, Mapping) or not _valid_hash(receipt.get("record_hash")):
            raise ResearchHandoffError("S7 record missing or untrusted")
        body = {k: v for k, v in receipt.items() if k != "record_hash"}
        if content_hash(body) != receipt["record_hash"]:
            raise ResearchHandoffError("S7 hash mismatch")
        if (
            receipt.get("session_id") != sid
            or receipt.get("generation") != n
            or receipt.get("original_generation_evidence_hash") != row["evidence_hash"]
            or receipt.get("study_scope") != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
        ):
            raise ResearchHandoffError("S7 generation binding mismatch")
        trials = receipt.get("report", {}).get("experiments")
        if (
            not isinstance(trials, list)
            or not isinstance(row.get("hypothesis_ids"), list)
            or sorted(t.get("hypothesis_id") for t in trials) != sorted(row["hypothesis_ids"])
        ):
            raise ResearchHandoffError("S7 hypothesis mismatch")


def _event(
    generation: dict[str, Any],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    hypotheses = {x["hypothesis_id"]: x for x in generation["experiments"]}
    experiments = []
    for trial in receipt["report"]["experiments"]:
        proposal = hypotheses[trial["hypothesis_id"]]
        experiments.append(
            {
                "hypothesis_id": trial["hypothesis_id"],
                "finding": trial["status"],
                "prediction": proposal.get("predicted_direction"),
                "measured_delta": trial.get("delta"),
                "metric": trial.get("metric"),
                "parent_fill_count": trial.get("parent_fill_count"),
                "child_fill_count": trial.get("child_fill_count"),
                "child_strategy_hash": trial.get("child_strategy_hash"),
                "mechanism_hypothesis_unproven": True,
                "alternative_explanation": proposal.get("alternative"),
                "observed_trade_ids": proposal.get("observed_ids", []),
                "needs_control_replay": trial.get("status") != "DIRECTION_MATCHED_DEVELOPMENT_ONLY",
            }
        )
    body = {
        "schema": "quant-l1-research-event-v1",
        "generation": generation["generation"],
        "evidence_hash": generation["evidence_hash"],
        "previous_evidence_hash": generation["previous_evidence_hash"],
        "s7_record_hash": receipt["record_hash"],
        "strategy_hash": generation.get("strategy_hash"),
        "effective_signal_hash": generation.get("effective_signal_hash"),
        "inherited_parent_hash": (
            generation["inherited_parent"].get("parent_strategy_hash")
            if isinstance(generation.get("inherited_parent"), Mapping)
            else None
        ),
        "measured_metrics": generation.get("metrics"),
        "experiments": experiments,
        "claims_causal_verified": False,
        "provenance": "NON_PIT_DEVELOPMENT_S7_NOT_INDEPENDENT",
    }
    return {**body, "event_hash": content_hash(body)}


def build_research_handoff(
    snapshot: Mapping[str, Any],
    s7_receipts: Mapping[int, Mapping[str, Any]],
    *,
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """Build evidence-linked L1 and a conservative L3 view; never truncate facts.

    Receipt input MUST come from Quant's validated canonical S7 read path.
    This function cannot authenticate how a caller acquired a signed report.
    """
    if type(max_chars) is not int or not 1000 <= max_chars <= 200_000:
        raise ResearchHandoffError("invalid model context budget")
    sid, history = _check_snapshot(snapshot)
    _check_receipts(sid, history, s7_receipts)
    try:
        learning = build_experiment_learning(history, s7_receipts, max_recent=50)
    except (ExperimentLearningError, ValueError, KeyError, TypeError) as exc:
        raise ResearchHandoffError("S7 learning provenance invalid") from exc
    events = [_event(row, s7_receipts[n]) for n, row in enumerate(history, 1)]
    negatives = [
        {
            "generation": e["generation"],
            "event_hash": e["event_hash"],
            "hypothesis_id": t["hypothesis_id"],
            "finding": t["finding"],
        }
        for e in events
        for t in e["experiments"]
        if t["finding"] != "DIRECTION_MATCHED_DEVELOPMENT_ONLY"
    ]
    head = history[-1]["evidence_hash"] if history else None
    brief = {
        "next_phase": snapshot["checkpoint_phase"],
        "last_three_events": events[-3:],
        "negative_and_unresolved_evidence": negatives,
        "next_test_priority": learning["next_test_priority"],
        "unverified_proposals_are_not_conclusions": True,
        "full_typed_schema_must_be_read_from_quant": True,
    }
    body = {
        "schema": "quant-evidence-memory-handoff-m0-v1",
        "session_id": sid,
        "completed_generations": snapshot["completed_generations"],
        "checkpoint_phase": snapshot["checkpoint_phase"],
        "dataset_hash": snapshot["dataset_hash"],
        "catalog_version": snapshot["catalog_version"],
        "source_evidence_head_hash": head,
        "s7_record_head_hash": s7_receipts[len(history)]["record_hash"] if history else None,
        "events": events,
        "brief": brief,
        "decision_mode": "NO_AUTOMATIC_STRATEGY_SELECTION",
        "genuine_provider_verified_generations": 0,
        "client_can_autonomously_start_chatgpt_turn": False,
        "data_scope": "NON_PIT_DEVELOPMENT_ONLY",
        "orders_enabled": False,
        "independent_oos_approved": False,
        "truncated": False,
    }
    # A full in-process result is NOT the compact tool response. Failing to fit
    # a budget demands a deliberate evidence lookup, not unsafe silent slicing.
    chars = len(json.dumps(brief, sort_keys=True, ensure_ascii=False))
    body["delivery_status"] = (
        "COMPACT_CANDIDATE_NOT_MODEL_VALIDATED"
        if chars <= max_chars
        else "ESCALATE_EVIDENCE_REPLAY"
    )
    body["brief_serialized_chars"] = chars
    body["max_brief_chars"] = max_chars
    return {**body, "handoff_hash": content_hash(body)}


def assert_handoff_fresh(
    handoff: Mapping[str, Any],
    current_snapshot: Mapping[str, Any],
) -> None:
    if not isinstance(handoff, Mapping) or content_hash(
        {k: v for k, v in handoff.items() if k != "handoff_hash"}
    ) != handoff.get("handoff_hash"):
        raise ResearchHandoffError("handoff integrity mismatch")
    sid, history = _check_snapshot(current_snapshot)
    if (
        handoff.get("session_id") != sid
        or handoff.get("source_evidence_head_hash")
        != (history[-1]["evidence_hash"] if history else None)
        or handoff.get("dataset_hash") != current_snapshot["dataset_hash"]
        or handoff.get("catalog_version") != current_snapshot["catalog_version"]
        or handoff.get("checkpoint_phase") != current_snapshot["checkpoint_phase"]
        or handoff.get("completed_generations") != current_snapshot["completed_generations"]
    ):
        raise ResearchHandoffError("stale handoff; rebuild from canonical evidence")


def compact_handoff_view(
    handoff: Mapping[str, Any],
    canonical_snapshot: Mapping[str, Any],
    s7_receipts: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    """Optional read-only small response; validate *all* canonical evidence again.

    This is not a public MCP endpoint or an authenticated model dispatch path.
    """
    assert_handoff_fresh(handoff, canonical_snapshot)
    rebuilt = build_research_handoff(
        canonical_snapshot,
        s7_receipts,
        max_chars=handoff["max_brief_chars"],
    )
    if rebuilt["handoff_hash"] != handoff["handoff_hash"]:
        raise ResearchHandoffError("canonical S7 report or research handoff changed")
    if handoff["delivery_status"] != "COMPACT_CANDIDATE_NOT_MODEL_VALIDATED":
        raise ResearchHandoffError("replay evidence required; no silent compact truncation")
    return {
        "schema": "quant-research-compact-view-m0-v1",
        "handoff_hash": handoff["handoff_hash"],
        "session_id": handoff["session_id"],
        "source_evidence_head_hash": handoff["source_evidence_head_hash"],
        "s7_record_head_hash": handoff["s7_record_head_hash"],
        "catalog_version": handoff["catalog_version"],
        "dataset_hash": handoff["dataset_hash"],
        "completed_generations": handoff["completed_generations"],
        "checkpoint_phase": handoff["checkpoint_phase"],
        "brief": handoff["brief"],
        "brief_serialized_chars": handoff["brief_serialized_chars"],
        "full_typed_plan_schema_required_separately": True,
        "ready_for_unattended_gpt_dispatch": False,
        "new_verified_provider_generations": 0,
        "orders_enabled": False,
        "independent_oos_approved": False,
    }

"""Cross-generation, explicit-workspace training alignment; no global DSR claim."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from memory.evidence_store import EvidenceIntegrityError, digest
from memory.training_trace_store import TrainingTraceStore, align_training_traces

RunSnapshot = dict[str, tuple[str, str, dict[str, Any]]]


def summarize_training_history(
    run_snapshots: dict[str, RunSnapshot],
    locations: dict[str, Path],
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"traces": [], "attempts": 0, "unrecorded": 0, "runs": set()}
    )
    for run_id, events in sorted(run_snapshots.items()):
        manifests = [payload for kind, _sha, payload in events.values() if kind == "manifest"]
        attempts = [payload for kind, _sha, payload in events.values() if kind == "attempt"]
        if not manifests:
            continue
        if len(manifests) != 1:
            raise EvidenceIntegrityError("conflicting training history manifest")
        manifest = manifests[0]
        group_key = manifest.get("comparison_key")
        if not isinstance(group_key, str) or not group_key:
            raise EvidenceIntegrityError("invalid training history comparison scope")
        group = groups[group_key]
        group["runs"].add(run_id)
        # Legacy manifests without full verifiable provenance cannot claim
        # comparable history; do not guess from a self-declared key.
        attrs = {k: value for k, value in manifest.items()
                 if k not in ("comparison_key", "research_run_id")}
        expected = ("dataset_hash", "data_zone", "timeframe", "calendar", "code_hash")
        manifest_valid = (
            all(isinstance(attrs.get(k), str) and attrs[k] for k in expected)
            and attrs.get("data_zone") == "development"
            and digest(attrs) == group_key
        )
        for attempt in attempts:
            group["attempts"] += 1
            reference = attempt.get("training_trace_ref")
            if reference is None:
                group["unrecorded"] += 1
                continue
            if not manifest_valid:
                raise EvidenceIntegrityError("unverified training history manifest")
            trace = TrainingTraceStore(locations[run_id]).read(reference)
            if (
                trace.dataset_hash != attrs["dataset_hash"]
                or trace.timeframe != attrs["timeframe"]
                or trace.calendar != attrs["calendar"]
            ):
                raise EvidenceIntegrityError("training trace source differs from manifest")
            identities = [
                candidate.get("semantic_strategy_hash")
                for candidate in attempt.get("candidates", [])
            ]
            if (
                not identities or any(not isinstance(s, str) for s in identities)
                or identities != [
                    candidate.semantic_strategy_hash for candidate in trace.candidates
                ]
            ):
                raise EvidenceIntegrityError("training trace candidate identity mismatch")
            group["traces"].append(trace)

    summaries = []
    complete = 0
    incomplete = 0
    for key, group in sorted(groups.items()):
        attempts = group["attempts"]
        observed = len(group["traces"])
        data: dict[str, Any] = {
            "comparison_key": key,
            "run_count": len(group["runs"]),
            "attempt_count": attempts,
            "trace_count": observed,
            "missing_trace_count": group["unrecorded"],
            "status": "NOT_MEASURED",
            "iid_equivalent_trials_estimate": None,
            "global_dsr_approved": False,
        }
        if group["unrecorded"]:
            data["status"] = "INCOMPLETE_TRAINING_TRACE_HISTORY"
            incomplete += 1
        elif observed < 2:
            data["status"] = "INSUFFICIENT_CROSS_GENERATION_HISTORY"
        else:
            aligned = align_training_traces(tuple(group["traces"]))
            data["status"] = aligned.status
            if aligned.status == "ALIGNED_TRAIN_ONLY":
                complete += 1
                data.update({
                    "aligned_observations": aligned.aligned_observations,
                    "candidate_evaluation_instances": aligned.candidate_evaluation_instances,
                    "unique_semantic_candidates": aligned.unique_semantic_candidates,
                    "duplicate_semantic_instances": aligned.duplicate_semantic_instances,
                    "training_cutoff_at": aligned.training_cutoff_at,
                })
                if aligned.cohort_dependence is not None:
                    details = asdict(aligned.cohort_dependence)
                    data.update({
                        "iid_equivalent_trials_estimate": details.get(
                            "iid_equivalent_trials_estimate"
                        ),
                        "iid_equivalent_trials_ci95": details.get(
                            "iid_equivalent_trials_ci95"
                        ),
                        "null_model": details.get("null_model"),
                    })
            else:
                incomplete += 1
        summaries.append(data)
    return {
        "cross_generation_aligned_scopes": complete,
        "cross_generation_incomplete_scopes": incomplete,
        "cross_generation_training_history": summaries[:32],
        "cross_generation_scope": "EXPLICIT_MANIFEST_MATCH_TRAIN_ONLY_NOT_GLOBAL_DSR",
    }

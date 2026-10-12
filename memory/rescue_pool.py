"""Rescue candidates reconstructed only from checksum-verified immutable Evidence.

REJECT candidates, unfinished attempts, mismatched data and unverified
strategy snapshots are never rescue inputs. This module cannot trade, promote,
read sealed OOS or alter acceptance gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.integrity.hashes import content_hash
from experiments.identity import semantic_strategy_hash
from memory.evidence_store import EvidenceStore
from memory.frontier import CandidateState
from memory.research_evidence import research_evidence
from strategy_ir.schema import StrategyIR
from strategy_ir.validator import validate_strategy


@dataclass(frozen=True)
class RescueEntry:
    candidate_hash: str
    parent_hash: str
    mutations: tuple[str, ...]
    failure_reason: str
    family: str


class RescuePool:
    def __init__(self) -> None:
        self._entries: dict[str, RescueEntry] = {}

    def add(self, entry: RescueEntry, *, status: CandidateState) -> None:
        if status is not CandidateState.NEAR_MISS:
            raise ValueError("Rescue Pool accepts only NEAR_MISS candidates")
        self._entries.setdefault(entry.candidate_hash, entry)

    def entries(self) -> tuple[RescueEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))


@dataclass(frozen=True)
class VerifiedRescue:
    candidate_hash: str
    source_run_id: str
    attempt_id: str
    dataset_hash: str
    comparison_key: str
    failed_gate: str
    strategy: StrategyIR


def near_miss_qualifies(candidate: dict[str, object]) -> bool:
    """A real funnel near miss missed just fast/full/robustness; other gates pass."""
    if candidate.get("status") != "NEAR_MISS":
        return False
    fails = candidate.get("failed_gates")
    if (
        not isinstance(fails, list)
        or len(fails) != 1
        or fails[0] not in {"fast", "full", "robustness"}
        or candidate.get("validation_evaluated") is not True
        or candidate.get("validation_passed") is not True
    ):
        return False
    gates = candidate.get("gates")
    if not isinstance(gates, list) or not gates:
        return False
    decisions: dict[str, bool] = {}
    for gate in gates:
        if not isinstance(gate, dict):
            return False
        name, passed = gate.get("name"), gate.get("passed")
        if not isinstance(name, str) or type(passed) is not bool or name in decisions:
            return False
        decisions[name] = passed
    return (
        decisions.get("validation") is True
        and decisions.get("risk") is True
        and {key for key, passed in decisions.items() if not passed} == {fails[0]}
    )


def verified_rescue_candidates(
    state_dir: Path,
    *,
    dataset_hash: str,
    comparison_key: str,
) -> tuple[VerifiedRescue, ...]:
    """Select closed-run, same-manifest NEAR_MISS IR snapshots without writing state.

    Snapshot checks happen independently of the Evidence checksum to ensure
    replayed IR really matches the same executable semantic hash. Missing or
    older snapshot shapes are ignored, never inferred from a REJECT.
    """
    if not dataset_hash or not comparison_key:
        return ()
    summaries = research_evidence(state_dir)["runs"]
    completed = {
        run["research_run_id"]
        for run in summaries
        if run["status"] == "COMPLETED" and run["comparison_key"] == comparison_key
    }
    events = EvidenceStore(state_dir).events()
    finalized = {
        (p["research_run_id"], p["attempt_id"])
        for event in events
        if event["kind"] == "generation"
        and (p := event["payload"])["research_run_id"] in completed
        and isinstance(p.get("attempt_id"), str)
        and p.get("status") == "COMPLETED"
    }
    candidates: dict[str, VerifiedRescue] = {}
    for event in events:
        if event["kind"] != "attempt":
            continue
        attempt = event["payload"]
        run_id, attempt_id = attempt["research_run_id"], attempt["attempt_id"]
        if (run_id, attempt_id) not in finalized or attempt["status"] != "COMPLETED":
            continue
        for row in attempt.get("candidates", []):
            if not near_miss_qualifies(row) or row.get("dataset_hash") != dataset_hash:
                continue
            identity, raw, recorded_hash = (
                row.get("candidate_hash"),
                row.get("strategy_ir"),
                row.get("strategy_ir_hash"),
            )
            if (
                not isinstance(identity, str)
                or len(identity) != 64
                or not isinstance(raw, dict)
                or not isinstance(recorded_hash, str)
                or content_hash(raw) != recorded_hash
            ):
                continue
            try:
                strategy = validate_strategy(StrategyIR.model_validate(raw))
            except (ValueError, TypeError):
                continue
            if (
                row.get("semantic_strategy_hash") != semantic_strategy_hash(strategy)
                or row.get("family") != strategy.family
            ):
                continue
            candidates.setdefault(
                identity,
                VerifiedRescue(
                    identity,
                    run_id,
                    attempt_id,
                    dataset_hash,
                    comparison_key,
                    row["failed_gates"][0],
                    strategy,
                ),
            )
    return tuple(candidates[k] for k in sorted(candidates))

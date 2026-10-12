"""Only replayable evaluator-approved NEAR_MISS Evidence may feed Rescue."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from application.research_hypothesis import propose_next_hypothesis
from core.integrity.hashes import content_hash
from experiments.candidate_generator import generate_candidates
from experiments.identity import semantic_strategy_hash
from memory.evidence_store import EvidenceStore
from memory.rescue_pool import verified_rescue_candidates
from orchestration.evaluation_runner import _candidate_snapshot_evidence
from tests.orchestration.test_train_only_selection import data, evaluate, strategy

HASH = "a" * 64
KEY = "comparable-development-run"


def _make_evidence(
    root: Path,
    *,
    status: str = "NEAR_MISS",
    dataset: str = HASH,
    key: str = KEY,
    corrupt: str | None = None,
    close: bool = True,
    validation_passed: bool = True,
) -> None:
    original = strategy()
    snapshot = original.model_dump(mode="json", by_alias=True)
    candidate = {
        "candidate_hash": "c" * 64,
        "semantic_strategy_hash": semantic_strategy_hash(original),
        "family": original.family,
        "status": status,
        "dataset_hash": dataset,
        "score": 0.4,
        "failed_gates": ["robustness"],
        "validation_evaluated": True,
        "validation_passed": validation_passed,
        "gates": [
            {"name": "robustness", "passed": False},
            {"name": "validation", "passed": validation_passed},
            {"name": "risk", "passed": True},
        ],
        "strategy_ir": snapshot,
        "strategy_ir_hash": content_hash(snapshot),
    }
    if corrupt == "hash":
        candidate["strategy_ir_hash"] = "b" * 64
    if corrupt == "semantic":
        candidate["semantic_strategy_hash"] = "b" * 64
    store = EvidenceStore(root)
    store.append(
        "run",
        "run:rescue",
        {
            "research_run_id": "rescue",
            "seed": 1,
            "requested_generations": 1,
        },
    )
    store.append(
        "manifest",
        "manifest:rescue",
        {
            "research_run_id": "rescue",
            "comparison_key": key,
        },
    )
    store.append(
        "attempt",
        "attempt:rescue",
        {
            "research_run_id": "rescue",
            "attempt_id": "rescue",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [candidate],
        },
    )
    if close:
        store.append(
            "generation",
            "generation:rescue:1",
            {
                "research_run_id": "rescue",
                "generation": 1,
                "status": "COMPLETED",
                "attempt_id": "rescue",
            },
        )
        store.append(
            "end",
            "end:rescue",
            {
                "research_run_id": "rescue",
                "status": "COMPLETED",
            },
        )


def test_snapshot_is_written_only_for_an_actual_gate_qualified_near_miss() -> None:
    result = evaluate(data())
    candidate, outcome = result.candidates[0], result.funnel[0]
    # Status alone is insufficient; no IR is exposed by an inconsistent label.
    mislabeled = _candidate_snapshot_evidence(candidate, replace(outcome, status="NEAR_MISS"))
    assert "strategy_ir" not in mislabeled
    # Only one genuine missed gate (robustness), with validation/risk passing.
    gates = tuple(
        replace(gate, passed=False) if gate.name == "robustness" else replace(gate, passed=True)
        for gate in outcome.gates
    )
    qualified = _candidate_snapshot_evidence(
        candidate, replace(outcome, status="NEAR_MISS", gates=gates)
    )
    assert qualified["strategy_ir_hash"] == content_hash(qualified["strategy_ir"])
    assert qualified["semantic_strategy_hash"] == semantic_strategy_hash(candidate.strategy)


def test_restore_completed_near_miss_from_immutable_evidence(tmp_path: Path) -> None:
    _make_evidence(tmp_path)
    restored = verified_rescue_candidates(
        tmp_path,
        dataset_hash=HASH,
        comparison_key=KEY,
    )
    assert len(restored) == 1
    assert restored[0].candidate_hash == "c" * 64
    assert restored[0].strategy == strategy()
    assert restored[0].source_run_id == "rescue"
    assert restored[0].failed_gate == "robustness"
    assert not (tmp_path / "rescue_pool.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"status": "REJECT"},
        {"status": "SURVIVOR"},
        {"dataset": "d" * 64},
        {"key": "other"},
        {"close": False},
        {"validation_passed": False},
        {"corrupt": "hash"},
        {"corrupt": "semantic"},
    ],
)
def test_refuse_unverifiable_or_ineligible_rescue(tmp_path: Path, change: dict) -> None:
    _make_evidence(tmp_path, **change)
    assert (
        verified_rescue_candidates(
            tmp_path,
            dataset_hash=HASH,
            comparison_key=KEY,
        )
        == ()
    )


def test_rescue_structural_fallback_uses_verified_near_miss_and_no_relabel(
    tmp_path: Path,
) -> None:
    from mutation.engine import MutationOperation, apply_operations

    _make_evidence(tmp_path)
    approved = verified_rescue_candidates(tmp_path, dataset_hash=HASH, comparison_key=KEY)[0]
    primary = strategy()
    # Use a slightly distinct primary so adopting the saved exit has novel semantics.
    primary = apply_operations(
        primary,
        [
            MutationOperation("CHANGE_EXIT", "exit.conditions.0.value", 99),
        ],
    )
    used = frozenset(
        {
            "ENTRY_THRESHOLD_EXPERIMENT_TIGHTER",
            "ENTRY_THRESHOLD_EXPERIMENT_LOOSER",
            "RISK_POSITION_SIZING_EXPERIMENT",
            "RISK_STOP_LOSS_EXPERIMENT",
            "RISK_TAKE_PROFIT_EXPERIMENT",
            "EXIT_THRESHOLD_EXPERIMENT_TIGHTER",
            "EXIT_THRESHOLD_EXPERIMENT_LOOSER",
            "INDICATOR_RSI_ENTRY_CONFIRMATION",
        }
    )
    hypothesis = propose_next_hypothesis(
        parent=primary,
        initial_operations=(),
        initial_domains=(),
        gate_names=("robustness",),
        prior_attempt_id="failed-current",
        used_hypotheses=used,
        already_evaluated=frozenset(),
        method="grid",
        count=1,
        next_seed=5,
        rescue=approved,
    )
    assert hypothesis is not None
    assert hypothesis.reason_code == "RESCUE_VERIFIED_NEAR_MISS_EXIT"
    assert hypothesis.summary()["rescue_source_candidate_hash"] == approved.candidate_hash
    candidate = generate_candidates(
        primary,
        hypothesis.operations,
        hypothesis.domains,
        method="grid",
        count=1,
        seed=5,
    )[0]
    assert candidate.strategy.exit == approved.strategy.exit

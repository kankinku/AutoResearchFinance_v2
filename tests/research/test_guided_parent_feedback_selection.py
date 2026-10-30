"""Regression: signed parent-child training outcomes must affect research parent ranks."""
from __future__ import annotations

import copy
from typing import Any

import pytest

from research.llm.guided_director_brief import (
    build_director_brief,
    summarize_parent_outcomes,
)


def _entry(generation: int, train_return: float, parent: int | None = None) -> dict[str, Any]:
    candidate = f"candidate{generation}"
    return {
        "run_id": f"run{generation}",
        "proposal_verified": True,
        "proposal": {"parent_run_id": f"run{parent}" if parent else None},
        "attempt": {
            "train_only_selection": {
                "sealed_oos_evaluated": False,
                "folds": [{
                    "selected_candidate_hash": candidate,
                    "selection_applied": True,
                    "train_total_return": train_return,
                    "train_end_at": "2022-12-28T00:00:00+00:00",
                    "test_start_at": "2022-12-29T00:00:00+00:00",
                }],
            },
            "candidates": [{
                "candidate_hash": candidate,
                "semantic_strategy_hash": f"{generation:064x}",
                "family": "trend" if generation < 3 else "momentum",
                "failed_gates": ["validation"],
            }],
        },
    }


def _control(generation: int, delta: float) -> dict[str, Any]:
    return {
        "generation": generation,
        "run_id": f"run{generation}",
        "orders_enabled": False,
        "sealed_oos_evaluated": False,
        "comparisons": [{"net_total_return_delta": delta}],
    }


def _brief(history: list[dict[str, Any]], outcomes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return build_director_brief(
        session_id="a" * 32,
        generation=len(history) + 1,
        checkpoint_token="b" * 32,
        history=history,
        learning={"evidence_digest": "c" * 64},
        controlled={"parent_outcomes": outcomes},
    )


def test_repeated_loss_parent_exits_exploitation_but_remains_diagnostic() -> None:
    # Parent 1 is high train return but all of its 3 real offspring lose.
    history = [_entry(1, 0.9), _entry(2, 0.6)]
    history += [_entry(i, -0.2, parent=1) for i in (3, 4, 5)]
    history += [_entry(i, -0.3, parent=2) for i in (6, 7, 8)]
    controls = [_control(i, 0.0) for i in (1, 2)]
    controls += [_control(i, -0.2) for i in (3, 4, 5)]
    controls += [_control(i, +0.2) for i in (6, 7, 8)]
    outcomes = summarize_parent_outcomes(history=history, controls=controls)
    assert outcomes["1"]["losses"] == 3
    assert outcomes["2"]["gains"] == 3
    brief = _brief(history, outcomes)
    exploit = [p["generation"] for p in brief["parent_lanes"]["TRAIN_ONLY_PERFORMANCE"]]
    assert 1 not in exploit
    assert 2 in exploit
    assert brief["parent_lanes"]["FAILED_HYPOTHESIS_REPAIR"]
    assert 1 in brief["repeated_loss_parent_generations"]
    assert brief["production_parent_promotion"] is False
    assert brief["sealed_oos_evaluated"] is False


def test_new_successful_offspring_changes_priority_without_test_data() -> None:
    history = [_entry(1, 0.6), _entry(2, 0.55)]
    history += [_entry(i, -0.2, parent=1) for i in (3, 4, 5)]
    history += [_entry(i, -0.2, parent=2) for i in (6, 7, 8)]
    controls = [_control(i, 0.0) for i in (1, 2)]
    controls += [_control(i, -0.2) for i in (3, 4, 5)]
    controls += [_control(i, +0.2) for i in (6, 7, 8)]
    baseline = _brief(history, summarize_parent_outcomes(history=history, controls=controls))
    assert baseline["parent_lanes"]["TRAIN_ONLY_PERFORMANCE"][0]["generation"] == 2
    changed = copy.deepcopy(controls)
    changed[2]["comparisons"][0]["net_total_return_delta"] = 0.2
    changed[3]["comparisons"][0]["net_total_return_delta"] = 0.2
    changed[4]["comparisons"][0]["net_total_return_delta"] = 0.2
    revised = _brief(history, summarize_parent_outcomes(history=history, controls=changed))
    assert revised["parent_lanes"]["TRAIN_ONLY_PERFORMANCE"][0]["generation"] == 1
    assert revised["context_digest"] != baseline["context_digest"]


def test_parent_outcome_integrity_and_no_unverified_fallback() -> None:
    history = [_entry(1, 0.5), _entry(2, 0.3, parent=1)]
    controls = [_control(1, 0.0), _control(2, -0.2)]
    assert summarize_parent_outcomes(history=history, controls=controls)["1"]["losses"] == 1
    broken = copy.deepcopy(controls)
    broken[1]["run_id"] = "different-run"
    with pytest.raises(ValueError, match="PARENT_OUTCOME_.*INTEGRITY"):
        summarize_parent_outcomes(history=history, controls=broken)
    broken = copy.deepcopy(history)
    broken[1]["proposal"]["parent_run_id"] = "unknown-run"
    with pytest.raises(ValueError, match="PARENT_OUTCOME_.*INTEGRITY"):
        summarize_parent_outcomes(history=broken, controls=controls)

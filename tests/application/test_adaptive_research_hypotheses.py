"""Tests for evidence-led, bounded mixed-mode replanning."""

from __future__ import annotations

import json
from pathlib import Path

from application.research_hypothesis import propose_next_hypothesis, verified_failed_gates
from mutation.parameter import ParameterDomain
from strategy_ir.schema import StrategyIR


def parent() -> StrategyIR:
    p = Path(__file__).resolve().parents[2] / "strategies/normalized/e8dad9397b1d9611-5.json"
    return StrategyIR.model_validate(json.loads(p.read_text(encoding="utf-8")))


def test_requires_verified_same_run_rejections() -> None:
    event = {
        "kind": "attempt",
        "id": "attempt:a",
        "payload": {
            "research_run_id": "r",
            "attempt_id": "a",
            "status": "COMPLETED",
            "execution": {"method": "random"},
            "candidates": [
                {
                    "candidate_hash": "x",
                    "semantic_strategy_hash": "a" * 64,
                    "status": "REJECT",
                    "failed_gates": ["robustness"],
                }
            ],
        },
    }
    assert verified_failed_gates((event,), run_id="r", attempt_id="a") == ("robustness",)
    assert verified_failed_gates((event,), run_id="wrong", attempt_id="a") is None
    event["payload"]["verification"] = "UNVERIFIED_EVALUATOR"
    assert verified_failed_gates((event,), run_id="r", attempt_id="a") is None


def test_failed_robustness_selects_new_candidates_deterministically() -> None:
    from experiments.candidate_generator import generate_candidates
    from experiments.identity import semantic_strategy_hash

    original = (ParameterDomain("indicators.disp_5.period", (3, 5, 8)),)
    before = generate_candidates(parent(), (), original, method="random", count=3, seed=8)
    seen = frozenset(semantic_strategy_hash(c.strategy) for c in before)
    args = dict(
        parent=parent(),
        initial_operations=(),
        initial_domains=original,
        gate_names=("robustness",),
        prior_attempt_id="a",
        used_hypotheses=frozenset(),
        already_evaluated=seen,
        method="random",
        count=3,
        next_seed=9,
    )
    plan = propose_next_hypothesis(**args)
    assert plan is not None and plan.preview_new_candidates > 0
    assert plan == propose_next_hypothesis(**args)


def test_validation_failure_changes_entry_threshold() -> None:
    plan = propose_next_hypothesis(
        parent=parent(),
        initial_operations=(),
        initial_domains=(),
        gate_names=("validation",),
        prior_attempt_id="a",
        used_hypotheses=frozenset(),
        already_evaluated=frozenset(),
        method="random",
        count=1,
        next_seed=9,
    )
    assert plan is not None and plan.operations[-1].op == "REPLACE_RULE"



def test_pending_adaptive_hypothesis_prevents_premature_exhaustion() -> None:
    from application.research_batch_service import _should_stop_exhausted_generation
    from application.research_hypothesis import LocalHypothesis

    pending = LocalHypothesis(
        reason_code="RISK_STOP_LOSS_EXPERIMENT",
        trigger_gate="robustness",
        applied_after_attempt_id="attempt-before",
        operations=(),
        domains=(ParameterDomain("risk.stop_loss_pct", (1.0, 2.0)),),
        preview_new_candidates=2,
    )
    for method, domains in (("grid", ()), ("random", ())):
        assert not _should_stop_exhausted_generation(
            result_status="NO_NEW_CANDIDATES",
            method=method,
            initial_domains=domains,
            pending_hypothesis=pending,
        )
    assert _should_stop_exhausted_generation(
        result_status="NO_NEW_CANDIDATES",
        method="grid",
        initial_domains=(),
        pending_hypothesis=None,
    )
    assert _should_stop_exhausted_generation(
        result_status="NO_NEW_CANDIDATES",
        method="random",
        initial_domains=(),
        pending_hypothesis=None,
    )
    assert not _should_stop_exhausted_generation(
        result_status="REJECT",
        method="grid",
        initial_domains=(),
        pending_hypothesis=None,
    )

"""Freeze matched AlgorithmPlan controls before observing their market results."""

from __future__ import annotations

import json
from pathlib import Path
from random import Random

from research.indicator_engine.algorithm_plan import AlgorithmPlan
from scripts.preregister_t4_equal_plan_comparison import (
    ENTRIES,
    REGIMES,
    SEED,
    digest,
    freeze,
    local_plan,
    random_plan,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/operations/evidence/quant-validation-20261020"


def test_frozen_manifest_reproduces_from_prior_gpt_evidence() -> None:
    previous = json.loads((EVIDENCE / "t4-connected-chatgpt-10gen.json").read_text())
    saved = json.loads((EVIDENCE / "t4-equal-plan-frozen-manifest.json").read_text())
    expected = freeze(previous)
    assert json.loads(json.dumps(expected)) == saved
    assert saved["freeze_hash"] == digest({k: v for k, v in saved.items() if k != "freeze_hash"})
    assert saved["control_result_not_yet_observed"] is True
    assert saved["design"] == "GPT_RETROSPECTIVE_RANDOM_LOCAL_PREREGISTERED"


def test_ten_per_arm_share_typed_indicator_universe_without_duplicates() -> None:
    recorded = json.loads((EVIDENCE / "t4-equal-plan-frozen-manifest.json").read_text())
    allowed = set(ENTRIES + REGIMES)
    assert len(recorded["plans"]) == 3
    for arm, plans in recorded["plans"].items():
        assert len(plans) == 10, arm
        assert len({digest(item) for item in plans}) == 10
        for plan in plans:
            typed = AlgorithmPlan.model_validate(plan)
            assert typed.position_size_pct == 100
            assert 1 <= len(typed.cases) <= 2
            for case in typed.cases:
                assert case.when.indicator_id in REGIMES
                assert all(vote.indicator_id in allowed for vote in case.votes)
                assert all(vote.indicator_id in ENTRIES for vote in case.votes)


def test_random_reproducible_but_local_is_precommitted_not_outcome_based() -> None:
    rng1, rng2 = Random(SEED), Random(SEED)
    assert [random_plan(rng1, i) for i in range(1, 11)] == [
        random_plan(rng2, i) for i in range(1, 11)
    ]
    assert [local_plan(i) for i in range(1, 11)] == [local_plan(i) for i in range(1, 11)]

"""P0-5 compares the SAME actionable rule/continuous-score search space."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.integrity.hashes import content_hash
from research.llm.fixed_budget_arms import (
    FixedBudgetError,
    build_fixed_budget_manifest,
    read_frozen_manifest,
    score_frozen_budget,
)
from scripts.t4_p05_real_session_three_arm import _parent_and_market, _source
from tests.research.test_fixed_budget_arm_comparison_p3_1 import _gpt

POLICY = "PLAN_VOTE_SCORE_MATCHED_COORDINATES_V2"


def test_matched_continuous_vote_controls_are_effective_searchable_rules(tmp_path: Path):
    parent, market = _parent_and_market(_source()[0], tmp_path)
    manifest = build_fixed_budget_manifest(
        parent,
        market,
        [_gpt(parent)],
        seed=20261019,
        source_evidence_hash="a" * 64,
        research_origin="SCRIPTED_TEMPLATE",
        control_policy=POLICY,
    )
    assert manifest["policy_version"] == POLICY
    assert manifest["model_identity_verified"] is False
    assert manifest["adaptive_reasoning_verified"] is False
    for row in manifest["candidates"]:
        if row["arm"] == "GPT_HISTORICAL":
            continue
        change = row["intent"]["operations"][0]
        assert change["path"] in {"entry.conditions.0", "exit.conditions.0"}
        assert change["condition"]["left"] == "plan_vote_score"
        assert 0.35 <= change["condition"]["value"] <= 0.90
    tested = score_frozen_budget(parent, market, manifest)
    assert tested["candidate_evaluations"] == 3
    assert tested["research_origin"] == "SCRIPTED_TEMPLATE"
    assert tested["model_identity_verified"] is False
    assert tested["statistical_superiority_established"] is False


def test_policy_tamper_and_unknown_model_identity_are_rejected(tmp_path: Path):
    parent, market = _parent_and_market(_source()[0], tmp_path)
    baseline = build_fixed_budget_manifest(
        parent,
        market,
        [_gpt(parent)],
        seed=2,
        source_evidence_hash="a" * 64,
        control_policy=POLICY,
    )
    changed = {**baseline, "policy_version": "RANDOM_UNIFORM_LOCAL_5PCT_RANGE_V1"}
    with pytest.raises(FixedBudgetError, match="hash"):
        score_frozen_budget(parent, market, changed)
    changed = {**baseline, "model_identity_verified": True}
    changed["freeze_hash"] = content_hash({k: v for k, v in changed.items() if k != "freeze_hash"})
    with pytest.raises(FixedBudgetError, match="scope|policy"):
        score_frozen_budget(parent, market, changed)
    with pytest.raises(FixedBudgetError, match="origin"):
        build_fixed_budget_manifest(
            parent,
            market,
            [_gpt(parent)],
            seed=2,
            source_evidence_hash="a" * 64,
            research_origin="VERIFIED_GPT_AUTONOMOUS",
        )


def test_g25_preregistered_model_intents_unchanged_in_matched_control() -> None:
    dir0 = Path("docs/operations/evidence")
    p1 = read_frozen_manifest(
        dir0 / "t4-p05-g25-fixed-5x3-20261019" / "fixed-budget-frozen-plan.json"
    )
    p2 = read_frozen_manifest(
        dir0 / "t4-p05-g25-matched-5x3-20261019" / "fixed-budget-frozen-plan.json"
    )
    assert p1["policy_version"] == "RANDOM_UNIFORM_LOCAL_5PCT_RANGE_V1"
    assert p2["policy_version"] == POLICY
    for a, b in zip(p1["candidates"][:5], p2["candidates"][:5], strict=True):
        assert a["arm"] == b["arm"] == "GPT_HISTORICAL"
        assert a["strategy_hash"] == b["strategy_hash"]
        assert a["intent"] == b["intent"]
    assert p1["source_gpt_evidence_hash"] == p2["source_gpt_evidence_hash"]
    assert p1["random_seed"] == p2["random_seed"]
    assert p2["candidates_per_arm"] == 5
    assert len(p2["candidates"]) == 15
    assert all(
        c["origin"] == "DETERMINISTIC_RESEARCH_CONTROL_NO_MODEL"
        for c in p2["candidates"]
        if c["arm"] != "GPT_HISTORICAL"
    )

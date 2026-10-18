"""P0-5 compares the SAME actionable rule/continuous-score search space."""

from __future__ import annotations

import sqlite3
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


@pytest.mark.parametrize(
    ("stem", "expected_hash", "expected_same_fill"),
    [
        (
            "t4-p05-g25-fixed-5x3-20261019",
            "dbc733184124f5431c9f256f13053b2b1870b462a9556f390d9a7ee60df9acb1",
            {"GPT_HISTORICAL": 0, "RANDOM": 5, "LOCAL_EVOLUTION": 5},
        ),
        (
            "t4-p05-g25-matched-5x3-20261019",
            "ec6fa28bffe4ac6ceb28fd9059e04cef5c27471a7b1edd947fe6d70333b17b19",
            {"GPT_HISTORICAL": 0, "RANDOM": 1, "LOCAL_EVOLUTION": 0},
        ),
    ],
)
def test_real_g25_frozen_studies_replay_without_modifying_canonical_53(
    tmp_path: Path,
    stem: str,
    expected_hash: str,
    expected_same_fill: dict[str, int],
) -> None:
    import json

    from scripts.t4_p05_real_session_three_arm import DB, SID, _parent_and_market, _source

    if not (DB / "cycles.sqlite").exists():
        pytest.skip("actual G25 53-generation Moon fixture not installed")
    source, report = _source()
    assert report["original_generation_evidence_hash"] == source["evidence_hash"]
    parent, market = _parent_and_market(source, tmp_path)
    frozen = read_frozen_manifest(
        Path("docs/operations/evidence") / stem / "fixed-budget-frozen-plan.json"
    )
    old_result = json.loads(
        (Path("docs/operations/evidence") / stem / "fixed-budget-results.json").read_text(
            encoding="utf-8"
        )
    )
    scored = score_frozen_budget(parent, market, frozen)
    assert scored == old_result
    assert scored["report_hash"] == expected_hash
    assert scored["model_identity_verified"] is False
    assert scored["adaptive_reasoning_verified"] is False
    assert scored["statistical_superiority_established"] is False
    assert scored["candidate_evaluations"] == 15
    assert all(a["evaluations"] == 5 for a in scored["arms"])
    assert {
        a["arm"]: a["same_fill_trace_as_parent_count"] for a in scored["arms"]
    } == expected_same_fill
    assert scored["benchmark"]["independent_oos_approved"] is False
    assert scored["automatic_parent_promotion"] is False
    with sqlite3.connect(f"file:{DB / 'cycles.sqlite'}?mode=ro", uri=True) as db:
        assert db.execute("select completed from sessions where id=?", (SID,)).fetchone()[0] == 53


def test_legacy_g179_frozen_20261017_source_replays_same_report_hash(tmp_path: Path) -> None:
    """Do not invalidate the P3-1 frozen G179 source while fixing P0-5 controls."""
    import json
    import sqlite3
    from dataclasses import replace

    from core.data.parquet import ParquetDataProvider
    from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
    from research.indicator_engine.catalog import ResearchCatalog
    from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
    from scripts.compare_fixed_budget_arms import _sources
    from strategy_ir.schema import StrategyIR

    root = Path("/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory")
    audit_root = root / "state/moon-http/research/audits"
    snapshot = audit_root / "phase1-20261017-1950"
    archive = audit_root / "fixed-budget-p3-1-20261017-v2"
    if (
        not (snapshot / "risk-replay-inputs.json").is_file()
        or not (archive / "fixed-budget-frozen-plan.json").is_file()
    ):
        pytest.skip("historical pinned G179 snapshot not present in environment")

    source, _s7 = _sources(snapshot, "2ba41aaeacd547319cfbf7e6f266ad11", 79)
    market = ParquetDataProvider.read(
        root / "data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet"
    )
    with (
        sqlite3.connect(
            f"file:{snapshot / 'catalog-for-risk-replay.sqlite'}?mode=ro", uri=True
        ) as old,
        sqlite3.connect(tmp_path / "catalog-copy.sqlite") as new,
    ):
        old.backup(new)
    base = compile_algorithm_plan(
        ResearchCatalog(tmp_path / "catalog-copy.sqlite"),
        AlgorithmPlan.model_validate(source["base_algorithm_plan"]),
        market,
    )
    ir = StrategyIR.model_validate(source["inherited_strategy_ir"])
    parent = replace(
        base.compiled,
        strategy=ir,
        strategy_hash=content_hash(ir.model_dump(mode="json", by_alias=True)),
    )
    assert parent.strategy_hash == source["strategy_hash"]
    assert audit_inherited_decisions(parent, market).trace_hash == source["audit_hash"]
    old_manifest = read_frozen_manifest(archive / "fixed-budget-frozen-plan.json")
    assert "research_origin" not in old_manifest
    assert old_manifest["freeze_hash"] == (
        "197bfe93fc9452bf22c37aaca8a16943fb7211ebb29cc06976517565ddfba8cc"
    )
    replay = score_frozen_budget(parent, market, old_manifest)
    prior = json.loads((archive / "fixed-budget-results.json").read_text(encoding="utf-8"))
    assert replay == prior
    assert replay["report_hash"] == (
        "0ea16cb21fbfec26533a0ade5a9e739cf8142e8c80250444a41922c8dda3b567"
    )

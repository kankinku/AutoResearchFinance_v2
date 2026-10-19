"""F2: bridge verified F1 evidence to explicit *unproven* weakness hypotheses."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.decision_audit import audit_compiled_academic_decisions
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.llm.feature_evidence_profile import build_verified_catalog_feature_profiles
from research.llm.loss_attribution import build_loss_attribution
from research.llm.weakness_feature_matcher import (
    WeaknessMatcherError,
    build_weakness_feature_guidance,
    match_weakness_to_profiles,
)
from tests.research.test_academic_decision_audit import _fixture


def _sources(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    catalog = ResearchCatalog(tmp_path / "f2_catalog.sqlite")
    seed_approved_references(catalog)
    for name in ("sma_direction", "previous_range_breakout", "parkinson_variance"):
        candidate = catalog.get_indicator(name)
        catalog.verify_and_register(name, verify_signal_on_synthetic_prices(candidate))
    return market, audit, catalog


def test_guidance_suggests_missing_information_not_automatic_filter(tmp_path: Path):
    market, audit, catalog = _sources(tmp_path)
    guided = build_weakness_feature_guidance(catalog, audit, market)
    assert guided == build_weakness_feature_guidance(catalog, audit, market)
    assert guided["schema"] == "weakness-feature-guidance-f2-v1"
    assert guided["dataset_hash"] == market.dataset_hash
    assert guided["source_audit_hash"] == audit.trace_hash
    assert guided["causal_status"] == "NOT_ESTABLISHED"
    assert guided["broker_executable"] is False
    assert guided["feature_profile_evidence_hash"]
    assert guided["guidance_hash"]
    assert len(guided["features"]) <= 3
    assert guided["recommended_auto_mutations"] == []
    assert "PARENT_UNCHANGED" in guided["comparison_options"]
    assert "FORMULA_NEW" in guided["comparison_options"]
    for f in guided["features"]:
        assert f["candidate_status"] in {
            "OBSERVED_CONTRADICTORY_OR_INSUFFICIENT",
            "NO_DIRECT_WEAKNESS_LINK",
        }
        assert f["formula_hash"]
        assert f["calculator"]
        assert f["candidate_strength_hypotheses"]
        assert isinstance(f["candidate_limitation_hypotheses"], list)
        if any(row["losses"] > 0 for row in f["observed_entry_states"]):
            assert f["candidate_limitation_hypotheses"]
        assert f["observation_sample"]["no_entry_decisions"] >= 0
        assert f["counterexamples"]
        assert f["evaluation_required"] == "S7_COSTED_PARENT_COMPARISON"
    for weakness in guided["weaknesses"]:
        assert weakness["weakness_id"]
        assert weakness["observed_trade_ids"]
        assert weakness["needed_information"]
        assert weakness["causal_status"] == "NOT_ESTABLISHED"
        assert weakness["parent_audit_hash"] == audit.trace_hash
        assert weakness["alternatives_to_test"]
        assert weakness["test_result"] == "NOT_RUN"


def test_no_loss_means_no_fabricated_weakness(tmp_path: Path):
    market, audit, catalog = _sources(tmp_path)
    raw = build_loss_attribution(audit, market)
    profiles = build_verified_catalog_feature_profiles(
        catalog, audit, market, ("sma_direction", "parkinson_variance")
    )
    empty = deepcopy(raw)
    empty["test_suggestions"] = []
    from core.integrity.hashes import content_hash

    empty["evidence_hash"] = content_hash({k: v for k, v in empty.items() if k != "evidence_hash"})
    result = match_weakness_to_profiles(empty, profiles)
    assert result["weaknesses"] == []
    assert result["recommended_auto_mutations"] == []


def test_tamper_mismatched_ancestors_and_profile_rejected(tmp_path: Path):
    market, audit, catalog = _sources(tmp_path)
    raw = build_loss_attribution(audit, market)
    profiles = build_verified_catalog_feature_profiles(
        catalog, audit, market, ("sma_direction", "parkinson_variance")
    )
    forged = deepcopy(profiles)
    forged["profiles"][0]["winning_entry_count"] += 9
    with pytest.raises(WeaknessMatcherError):
        match_weakness_to_profiles(raw, forged)
    forged = deepcopy(raw)
    forged["dataset_hash"] = "f" * 64
    with pytest.raises(WeaknessMatcherError):
        match_weakness_to_profiles(forged, profiles)
    with pytest.raises(WeaknessMatcherError):
        match_weakness_to_profiles(raw, {**profiles, "source_audit_hash": "f" * 64})


def test_followup_mcp_context_includes_read_only_guidance(tmp_path: Path):
    from tests.integrations.test_academic_mcp_sessions import _setup
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    server, started = _setup(tmp_path)
    assert "feature_weakness_guidance" not in started["model_context"]
    writer = ScriptedResearcher()
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": writer.propose(started["model_context"]),
        },
    )
    outcome = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": writer.propose(staged["model_context"]),
        },
    )
    assert outcome["completed_generations"] == 1
    guide = outcome["model_context"]["feature_weakness_guidance"]
    assert guide["source_generation_evidence_hash"] == outcome["history"][-1]["evidence_hash"]
    assert guide["source_audit_hash"] == outcome["history"][-1]["audit_hash"]
    assert guide["recommended_auto_mutations"] == []
    assert guide["broker_executable"] is False
    # S2 was already bound before F2 was presented; no signed S2 rewrite.
    assert (
        outcome["history"][-1]["diagnostic_context_hash"] == staged["model_context"]["context_hash"]
    )

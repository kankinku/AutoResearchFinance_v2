"""F1: observation-only feature profiles must be bounded, reproducible and non-causal."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.data.contracts import DataZone, MarketDataSet
from research.indicator_engine.decision_audit import audit_compiled_academic_decisions
from research.llm.feature_evidence_profile import (
    FeatureProfileError,
    build_feature_evidence_profiles,
)
from tests.research.test_academic_decision_audit import _fixture


def test_two_verified_audited_signals_profile_outcomes_and_no_entry(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    names = tuple(sorted(dict(audit.decisions[-1].indicator_values)))
    report = build_feature_evidence_profiles(audit, market, names)
    assert report == build_feature_evidence_profiles(audit, market, names)
    assert report["schema"] == "feature-evidence-profile-f1-v1"
    assert report["source_audit_hash"] == audit.trace_hash
    assert report["dataset_hash"] == market.dataset_hash
    assert report["coverage_scope"] == "AUDITED_REPLAY_SIGNALS_ONLY"
    assert report["validation_scope"] == "REUSED_DEVELOPMENT_ONLY"
    assert report["causal_status"] == "NOT_ESTABLISHED"
    assert report["broker_executable"] is False
    assert len(report["profiles"]) == len(names) == 2
    for profile in report["profiles"]:
        assert profile["feature_id"] in names
        assert profile["signal_observation_count"] + profile["missing_count"] == len(
            audit.decisions
        )
        assert profile["no_entry_decision_count"] > 0
        assert profile["no_entry_decision_examples"]
        assert profile["winning_entry_count"] + profile["losing_entry_count"] + profile[
            "flat_entry_count"
        ] == len(audit.round_trips)
        conditional = profile["entry_outcomes_by_observed_signal"]
        assert sum(x["wins"] for x in conditional) == profile["winning_entry_count"]
        assert sum(x["losses"] for x in conditional) == profile["losing_entry_count"]
        assert sum(x["flats"] for x in conditional) == profile["flat_entry_count"]
        assert (
            sum(x["wins"] for x in profile["signal_conditioned_regime_counts"])
            == (profile["winning_entry_count"])
        )
        assert profile["role_claim"] == "UNSPECIFIED_OBSERVED_SIGNAL"
        assert profile["advantages_not_proven"] is True
        assert profile["limitations_not_proven"] is True
        assert profile["evidence_status"] in {"OBSERVED_INSUFFICIENT_SAMPLE", "OBSERVED_NON_CAUSAL"}
        assert profile["formula_provenance_status"] == "AUDIT_VECTOR_ONLY"
        assert profile["signal_asof"] == "BAR_CLOSE_BEFORE_NEXT_OPEN"
        assert profile["profile_hash"]
        assert all(item["source_decision_id"] for item in profile["regime_observations"])
    assert report["evidence_hash"]


def test_unknown_duplicate_too_many_features_and_nonfinite_rejected(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    name = audit.decisions[-1].indicator_values[0][0]
    with pytest.raises(FeatureProfileError):
        build_feature_evidence_profiles(audit, market, ("missing_indicator",))
    with pytest.raises(FeatureProfileError):
        build_feature_evidence_profiles(audit, market, (name, name))
    with pytest.raises(FeatureProfileError):
        build_feature_evidence_profiles(audit, market, ())
    with pytest.raises(FeatureProfileError):
        build_feature_evidence_profiles(audit, market, tuple("abcdefgh"))
    with pytest.raises(FeatureProfileError):
        build_feature_evidence_profiles(audit, market, (name,), threshold=float("nan"))


def test_sealed_tampered_and_wrong_market_fail_closed(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    name = audit.decisions[-1].indicator_values[0][0]
    with pytest.raises(FeatureProfileError):
        build_feature_evidence_profiles(replace(audit, trace_hash="f" * 64), market, (name,))
    with pytest.raises(FeatureProfileError):
        build_feature_evidence_profiles(
            audit, MarketDataSet(market.version, DataZone.SEALED_OOS, market.bars), (name,)
        )
    with pytest.raises(FeatureProfileError):
        build_feature_evidence_profiles(audit, replace(market, bars=market.bars[:-1]), (name,))


def test_profile_uses_signal_at_entry_not_eventual_exit_and_marks_uncertainty(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    name = audit.decisions[-1].indicator_values[0][0]
    report = build_feature_evidence_profiles(audit, market, (name,), min_per_outcome=100)
    profile = report["profiles"][0]
    assert profile["evidence_status"] == "OBSERVED_INSUFFICIENT_SAMPLE"
    for group in profile["regime_observations"]:
        assert group["outcome"] in {"WIN", "LOSS", "FLAT"}
        assert group["source_decision_id"] in {d.decision_id for d in audit.decisions}
        assert group["signal_time"] < group["first_fill_time"]
    # Outcome can label retrospective research, never a live feature or exit rule.
    assert profile["outcomes_are_ex_post_labels"] is True
    assert profile["independent_oos_approved"] is False


def test_three_verified_academic_features_expose_true_formula_identity(tmp_path: Path):
    from research.indicator_engine.catalog import ResearchCatalog
    from research.indicator_engine.seed import seed_approved_references
    from research.indicator_engine.signals import verify_signal_on_synthetic_prices
    from research.llm.feature_evidence_profile import build_verified_catalog_feature_profiles

    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    catalog = ResearchCatalog(tmp_path / "feature_catalog.sqlite")
    seed_approved_references(catalog)
    names = ("sma_direction", "previous_range_breakout", "parkinson_variance")
    for name in names:
        candidate = catalog.get_indicator(name)
        catalog.verify_and_register(name, verify_signal_on_synthetic_prices(candidate))
    result = build_verified_catalog_feature_profiles(catalog, audit, market, names)
    assert result == build_verified_catalog_feature_profiles(catalog, audit, market, names)
    assert result["coverage_scope"] == "VERIFIED_ACADEMIC_REFERENCE_AND_AUDITED_OUTCOMES"
    assert [r["feature_id"] for r in result["profiles"]] == list(names)
    assert all(p["formula_metadata"]["candidate_hash"] for p in result["profiles"])
    assert all(p["formula_metadata"]["license_attested"] is False for p in result["profiles"])
    assert all(p["independent_oos_approved"] is False for p in result["profiles"])
    assert result["profiles"][2]["binary_signal"] is False
    assert len(result["pairwise_observation_agreement"]) == 3

    other_catalog = ResearchCatalog(tmp_path / "unverified_catalog.sqlite")
    seed_approved_references(other_catalog)
    with pytest.raises(FeatureProfileError):
        build_verified_catalog_feature_profiles(other_catalog, audit, market, names)
    with pytest.raises(FeatureProfileError):
        build_verified_catalog_feature_profiles(
            catalog, audit, replace(market, bars=market.bars[:-1]), names
        )

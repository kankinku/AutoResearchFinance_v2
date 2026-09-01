from __future__ import annotations

import pytest

from evaluation.benchmark import compare_benchmarks
from evaluation.risk import RiskEvaluation
from evaluation.selector import FunnelResult, GateDecision
from memory.knowledge import compress_knowledge, extract_knowledge


def _result(candidate_hash: str, status: str, score: float) -> FunnelResult:
    return FunnelResult(
        candidate_hash,
        "trend",
        status,
        score,
        (GateDecision("fast", status != "REJECT", 1, 2, None),),
    )


def test_knowledge_extraction_keeps_hashes_and_abstract_profiles_only() -> None:
    knowledge = extract_knowledge(
        generation=4,
        results=(_result("good", "SURVIVOR", 0.8), _result("bad", "REJECT", 0.1)),
    )

    assert knowledge["known_good"][0]["candidate_hash"] == "good"
    assert knowledge["known_bad"][0]["candidate_hash"] == "bad"
    assert "raw_text" not in str(knowledge)
    assert "source_path" not in str(knowledge)


def test_knowledge_compression_is_bounded_and_retains_unexplored_profiles() -> None:
    knowledge = extract_knowledge(
        generation=1,
        results=(_result("near", "NEAR_MISS", 0.4),),
    )
    compressed = compress_knowledge(knowledge, max_items=1)

    assert len(compressed["unexplored"]) == 1
    assert compressed["schema_version"] == 1


def test_knowledge_keeps_feature_benchmark_and_risk_facts_abstract() -> None:
    benchmark = compare_benchmarks((100.0, 110.0), (100.0, 105.0), (100.0, 106.0))
    result = FunnelResult(
        "feature-good",
        "macro",
        "SURVIVOR",
        0.8,
        (GateDecision("fast", True, 1, 2, None),),
        full_benchmark=benchmark,
        risk_evaluation=RiskEvaluation(0.4, None, 2.0, "stop", 1.0, 0, True),
        feature_ids=("vix_percentile", "us_10y_change"),
    )

    profile = extract_knowledge(generation=5, results=(result,))["known_good"][0]

    assert profile["feature_ids"] == ("us_10y_change", "vix_percentile")
    assert profile["qqq_excess_return"] == pytest.approx(0.05)
    assert profile["risk_compliant"] is True

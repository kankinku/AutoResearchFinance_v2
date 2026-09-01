from __future__ import annotations

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

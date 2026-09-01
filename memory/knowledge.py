from __future__ import annotations

from typing import Any

from evaluation.selector import FunnelResult


def extract_knowledge(*, generation: int, results: tuple[FunnelResult, ...]) -> dict[str, Any]:
    if generation < 0:
        raise ValueError("generation cannot be negative")
    known_good = [
        _profile(result, generation)
        for result in results
        if result.status in {"SURVIVOR", "FRONTIER"}
    ]
    known_bad = [_profile(result, generation) for result in results if result.status == "REJECT"]
    unexplored = [
        _profile(result, generation) for result in results if result.status == "NEAR_MISS"
    ]
    return {
        "schema_version": 1,
        "generation": generation,
        "known_good": sorted(known_good, key=lambda item: item["candidate_hash"]),
        "known_bad": sorted(known_bad, key=lambda item: item["candidate_hash"]),
        "unexplored": sorted(unexplored, key=lambda item: item["candidate_hash"]),
    }


def compress_knowledge(knowledge: dict[str, Any], *, max_items: int) -> dict[str, Any]:
    if max_items <= 0:
        raise ValueError("max_items must be positive")
    return {
        "schema_version": int(knowledge.get("schema_version", 1)),
        "generation": int(knowledge.get("generation", 0)),
        **{
            name: list(knowledge.get(name, []))[:max_items]
            for name in ("known_good", "known_bad", "unexplored")
        },
    }


def _profile(result: FunnelResult, generation: int) -> dict[str, Any]:
    return {
        "candidate_hash": result.candidate_hash,
        "family": result.family,
        "status": result.status,
        "score": result.score,
        "generation": generation,
        "failed_gates": tuple(gate.name for gate in result.gates if not gate.passed),
    }

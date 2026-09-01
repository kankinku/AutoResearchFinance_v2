from __future__ import annotations

from collections import Counter
from typing import Any

from evaluation.selector import FunnelResult


def summarize_results(results: tuple[FunnelResult, ...]) -> dict[str, Any]:
    ordered = sorted(results, key=lambda result: (-result.score, result.candidate_hash))
    counts = dict(sorted(Counter(result.status for result in results).items()))
    survivors = [result for result in ordered if result.status in {"SURVIVOR", "FRONTIER"}]
    champion = _abstract(survivors[0]) if survivors else None
    frontier = [_abstract(result) for result in survivors[:10]]
    return {
        "tested": len(results),
        "valid": sum(result.status != "REJECT" for result in results),
        "counts": counts,
        "champion": champion,
        "frontier": frontier,
        "evidence": "OK" if len(survivors) >= 3 else "INSUFFICIENT_EVIDENCE",
    }


def _abstract(result: FunnelResult) -> dict[str, Any]:
    return {
        "candidate_hash": result.candidate_hash,
        "family": result.family,
        "score": result.score,
        "status": result.status,
    }

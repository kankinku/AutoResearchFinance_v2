from __future__ import annotations

from typing import Any


def select_candidate_frontier(
    *,
    prescreen_results: list[dict[str, Any]],
    candidate_limit: int,
    promotion_limit: int,
) -> list[dict[str, Any]]:
    ranked = sorted(
        prescreen_results,
        key=lambda item: (
            0 if bool(item.get("passed")) else 1,
            -float(item.get("score", 0.0)),
            str(item.get("candidate_id", "")),
        ),
    )
    promoted_ids: set[str] = set()
    passing = [item for item in ranked if bool(item.get("passed"))]
    for item in passing[:promotion_limit]:
        promoted_ids.add(str(item.get("candidate_id", "")))
    frontier: list[dict[str, Any]] = []
    for index, item in enumerate(ranked, start=1):
        within_candidate_limit = index <= candidate_limit
        frontier.append(
            {
                **item,
                "rank": index,
                "promoted": within_candidate_limit
                and str(item.get("candidate_id", "")) in promoted_ids,
            }
        )
    return frontier

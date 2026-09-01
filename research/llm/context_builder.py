from __future__ import annotations

from typing import Any


def build_context(
    *,
    generation: int,
    champion: dict[str, Any] | None,
    frontier: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    feature_catalog: list[dict[str, Any]] | None = None,
    raw_market_rows: list[dict[str, Any]] | None = None,
    sealed_oos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    del raw_market_rows, sealed_oos
    return {
        "generation": generation,
        "champion": champion,
        "frontier": frontier,
        "observations": observations,
        "feature_catalog": feature_catalog or [],
    }


def should_call_llm(
    *, generation_start: bool, plateau: bool, new_family: bool, new_primitive: bool
) -> bool:
    return generation_start or plateau or new_family or new_primitive

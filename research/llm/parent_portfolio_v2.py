"""Opt-in counted-generation parent portfolio (development only).

This module never grants OOS or broker permissions. Its candidate shortlist
only guides *which* costly original-evidence replays to attempt. Final picks
require exact replay by the academic checkpoint service.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any


def shortlist_counted_generations(
    history: Sequence[Mapping[str, Any]], *, per_lane: int = 8
) -> list[dict[str, Any]]:
    """Return diverse recorded generations to VERIFY, not preapproved parents.

    Every slot in the three scoring lanes receives independent replay in the
    caller. Multiple signals with the same effective vector are de-duplicated.
    No validation/OOS data is accessed to construct this shortlist.
    """
    if not 1 <= per_lane <= 20:
        raise ValueError("per_lane must be 1..20")
    eligible: list[dict[str, Any]] = []
    for row in history:
        metrics = row.get("metrics")
        if not row.get("inherited_strategy_ir") or not isinstance(metrics, dict):
            continue
        fields = ("total_return", "max_drawdown", "exposure", "calmar")
        if any(
            isinstance(metrics.get(k), bool)
            or not isinstance(metrics.get(k), (float, int))
            or not isfinite(float(metrics[k]))
            for k in fields
        ):
            continue
        if (
            int(metrics.get("trade_count", -1)) < 30
            or metrics["total_return"] < 0.3
            or not 0 <= metrics["max_drawdown"] <= 0.5
            or not 0.05 <= metrics["exposure"] <= 1
        ):
            continue
        if not row.get("effective_signal_hash"):
            continue
        eligible.append(dict(row))
    lanes = (
        sorted(eligible, key=lambda x: (-x["metrics"]["total_return"], x["generation"])),
        sorted(eligible, key=lambda x: (-x["metrics"]["calmar"], x["generation"])),
        sorted(
            (x for x in eligible if x["metrics"]["total_return"] >= 0.5),
            key=lambda x: (x["metrics"]["max_drawdown"], -x["metrics"]["total_return"]),
        ),
    )
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lane in lanes:
        count = 0
        for candidate in lane:
            signal = str(candidate["effective_signal_hash"])
            if signal in seen:
                continue
            result.append(candidate)
            seen.add(signal)
            count += 1
            if count == per_lane:
                break
    return result


def verified_parent_lanes(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic Pareto-aware lanes from VERIFIED replayed candidates only.

    Return, return/drawdown and drawdown are different objectives. Three
    distinct effective signals are selected when such candidates exist.
    """
    if not candidates:
        return []
    items = list(candidates)
    if any(c.get("replay_verified") is not True for c in items):
        raise ValueError("unverified parent was supplied")
    # True two-objective Pareto frontier: no candidate with at least as much
    # development return AND no greater drawdown is sacrificed to a dominated
    # strategy. Identical return/drawdown candidates resolve deterministically.
    items.sort(key=lambda x: x["source_generation"])
    frontier = []
    for row in items:
        quality = row["parent_quality"]
        if any(
            (
                other["parent_quality"]["total_return"] >= quality["total_return"]
                and other["parent_quality"]["max_drawdown"] <= quality["max_drawdown"]
                and (
                    other["parent_quality"]["total_return"] > quality["total_return"]
                    or other["parent_quality"]["max_drawdown"] < quality["max_drawdown"]
                    or (
                        other["source_generation"] < row["source_generation"]
                        and other["parent_quality"]["total_return"] == quality["total_return"]
                        and other["parent_quality"]["max_drawdown"] == quality["max_drawdown"]
                    )
                )
            )
            for other in items
            if other is not row
        ):
            continue
        frontier.append(row)
    items = frontier
    ranks = (
        sorted(
            items,
            key=lambda x: (
                -x["parent_quality"]["total_return"],
                x["parent_quality"]["max_drawdown"],
            ),
        ),
        sorted(
            items,
            key=lambda x: (
                -x["parent_quality"]["total_return"]
                / max(x["parent_quality"]["max_drawdown"], 0.01),
                -x["parent_quality"]["total_return"],
            ),
        ),
        sorted(
            (x for x in items if x["parent_quality"]["total_return"] >= 0.5),
            key=lambda x: (
                x["parent_quality"]["max_drawdown"],
                -x["parent_quality"]["total_return"],
            ),
        ),
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lane in ranks:
        for row in lane:
            key = str(row["effective_signal_hash"])
            if key not in seen:
                seen.add(key)
                out.append(dict(row))
                break
    return out


def choose_parent_lane(
    candidates: Sequence[Mapping[str, Any]], next_generation: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Rotate *only verified eligible* parents, never force failed strategies."""
    if type(next_generation) is not int or next_generation < 2:
        raise ValueError("invalid next generation")
    lanes = verified_parent_lanes(candidates)
    if not lanes:
        raise ValueError("no verified parent candidates")
    return lanes[(next_generation - 1) % len(lanes)], lanes

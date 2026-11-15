"""Synthetic, zero-market-data equal-budget parent-selection comparison.

This replays pure selection functions, NOT old G1-G150, historical returns,
live backtests, hypothetical alpha, or an actual autonomous GPT experiment.
"""

from __future__ import annotations

import json
from collections import Counter
from inspect import signature
from random import Random
from typing import Any

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.integrity.hashes import content_hash
from research.llm.lineage_selection import choose_development_parent
from research.llm.parent_portfolio_v2 import choose_parent_lane, verified_parent_lanes


def _digest(generation: int, label: str) -> str:
    return content_hash({"synthetic": True, "g": generation, "kind": label})


def _fictional_candidates() -> list[dict[str, Any]]:
    # ID labels evoke the observed concentration issue but ALL numbers and
    # evidence hashes are synthetic; no former-session file is accessed.
    profiles = (
        (94, 0.80, 0.23, 35, 0.35, 0.50, 0.30),
        (96, 0.67, 0.09, 45, 0.25, 0.40, 0.15),
        (106, 0.76, 0.14, 40, 0.30, 0.55, 0.19),
        (130, 0.72, 0.16, 38, 0.35, 0.50, 0.20),
    )
    rows: list[dict[str, Any]] = []
    for generation, ret, dd, trades, exposure, child_ret, child_dd in profiles:
        rows.append({
            "source_generation": generation,
            "source_evidence_hash": _digest(generation, "evidence"),
            "lineage_report_hash": _digest(generation, "lineage"),
            "successor_strategy_hash": _digest(generation, "strategy"),
            "strategy_equity_hash": _digest(generation, "equity"),
            "effective_signal_hash": _digest(generation, "effective_signal"),
            "executed_fill_hash": _digest(generation, "canonical_fills"),
            "child_total_return": child_ret,
            "successor_total_return": ret,
            "child_max_drawdown": child_dd,
            "successor_max_drawdown": dd,
            "successor_closed_trades": trades,
            "successor_market_exposure": exposure,
            "qqq_buy_and_hold_return": 1.0,
            "qqq_exposure_matched_return": 0.50,
            "parent_quality": {
                "total_return": ret,
                "max_drawdown": dd,
                "closed_trades": trades,
                "market_exposure": exposure,
            },
            "replay_verified": True,  # A fixture assumption, not a live replay.
            "independent_oos_approved": False,
            "broker_executable": False,
        })
    return rows


def compare_synthetic_parent_selection(*, seed: int = 20261110) -> dict[str, Any]:
    """Compare identical selection opportunities; no price data is loaded."""
    if type(seed) is not int:
        raise ValueError("integer seed required")
    actual_default = signature(AcademicMCPCheckpointService).parameters[
        "parent_portfolio_v2"
    ].default
    if actual_default is not False:
        raise ValueError("production default was unexpectedly changed")
    candidates = _fictional_candidates()
    Random(seed).shuffle(candidates)
    generations = tuple(range(126, 151))
    legacy = []
    diverse = []
    for generation in generations:
        baseline = choose_development_parent(candidates)
        if baseline is None:
            raise ValueError("synthetic baseline pool has no eligible parents")
        selected, _ = choose_parent_lane(candidates, generation)
        legacy.append(baseline)
        diverse.append(selected)
    all_lanes = verified_parent_lanes(candidates)
    fill_by_generation = {c["source_generation"]: c["executed_fill_hash"] for c in candidates}

    def _summary(chosen: list[dict[str, Any]]) -> dict[str, Any]:
        parent_counts = Counter(str(row["source_generation"]) for row in chosen)
        return {
            "selection_count": len(chosen),
            "parent_counts": dict(sorted(parent_counts.items())),
            "max_parent_concentration": max(parent_counts.values()) / len(chosen),
            "distinct_executed_fill_hashes": len({
                fill_by_generation[row["source_generation"]] for row in chosen
            }),
            "lowest_selected_development_drawdown": min(
                row["parent_quality"]["max_drawdown"] for row in chosen
            ),
        }

    body: dict[str, Any] = {
        "schema": "t4-synthetic-parent-selector-equal-budget-v1",
        "status": "EXPERIMENTAL_SELECTION_ONLY",
        "synthetic_only": True,
        "not_historical_g94_g96_g106_evidence": True,
        "past_experiments_used_as_parent_or_memory": False,
        "candidate_fixture_hash": content_hash(candidates),
        "fixed_random_seed": seed,
        "candidate_count_each_arm": len(candidates),
        "selection_opportunities_each_arm": len(generations),
        "candidate_scoring_slots_each_arm": len(candidates) * len(generations),
        "verified_replay_assumed_not_executed": True,
        "actual_backtests_executed": 0,
        "llm_calls": 0,
        "hypothesis_direction_match_rate": None,
        "actual_new_replayed_signals": None,
        "observed_backtest_cost_usd": None,
        "actual_model_token_cost_usd": None,
        "independent_oos_approved": False,
        "superiority_demonstrated": False,
        "default_parent_portfolio_v2_unchanged": actual_default is False,
        "lane_count": len(all_lanes),
        "legacy": _summary(legacy),
        "opt_in": _summary(diverse),
    }
    return {**body, "report_hash": content_hash(body)}


if __name__ == "__main__":
    print(json.dumps(compare_synthetic_parent_selection(), indent=2, sort_keys=True))

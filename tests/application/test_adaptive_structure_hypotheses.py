"""Structural fallback candidates for evidence-guided local research."""

from __future__ import annotations

import json
from pathlib import Path

from application.research_hypothesis import propose_next_hypothesis
from experiments.candidate_generator import generate_candidates
from experiments.identity import semantic_strategy_hash
from strategy_ir.schema import StrategyIR


def _parent() -> StrategyIR:
    path = Path(__file__).resolve().parents[2] / "strategies/normalized/e8dad9397b1d9611-5.json"
    return StrategyIR.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _plan(used: frozenset[str]):
    return propose_next_hypothesis(
        parent=_parent(),
        initial_operations=(),
        initial_domains=(),
        gate_names=("annual_trade_count", "validation"),
        prior_attempt_id="verified-attempt",
        used_hypotheses=used,
        already_evaluated=frozenset(),
        method="grid",
        count=1,
        next_seed=31,
    )


def test_exit_rules_replan_after_local_entry_and_risk_menu() -> None:
    used = frozenset(
        {
            "ENTRY_THRESHOLD_EXPERIMENT_TIGHTER",
            "ENTRY_THRESHOLD_EXPERIMENT_LOOSER",
            "RISK_POSITION_SIZING_EXPERIMENT",
            "RISK_STOP_LOSS_EXPERIMENT",
            "RISK_TAKE_PROFIT_EXPERIMENT",
        }
    )
    plan = _plan(used)
    assert plan is not None
    assert plan.reason_code.startswith("EXIT_THRESHOLD_EXPERIMENT_")
    candidate = generate_candidates(
        _parent(), plan.operations, plan.domains, method="grid", count=1, seed=31
    )[0]
    assert candidate.strategy.exit != _parent().exit
    assert candidate.strategy.entry == _parent().entry
    assert semantic_strategy_hash(candidate.strategy) != semantic_strategy_hash(_parent())


def test_indicator_combination_is_a_real_entry_structure_change() -> None:
    used = frozenset(
        {
            "ENTRY_THRESHOLD_EXPERIMENT_TIGHTER",
            "ENTRY_THRESHOLD_EXPERIMENT_LOOSER",
            "RISK_POSITION_SIZING_EXPERIMENT",
            "RISK_STOP_LOSS_EXPERIMENT",
            "RISK_TAKE_PROFIT_EXPERIMENT",
            "EXIT_THRESHOLD_EXPERIMENT_TIGHTER",
            "EXIT_THRESHOLD_EXPERIMENT_LOOSER",
        }
    )
    plan = _plan(used)
    assert plan is not None
    assert plan.reason_code == "INDICATOR_RSI_ENTRY_CONFIRMATION"
    candidate = generate_candidates(
        _parent(), plan.operations, plan.domains, method="grid", count=1, seed=31
    )[0]
    assert len(candidate.strategy.indicators) == len(_parent().indicators) + 1
    assert len(candidate.strategy.entry.conditions) == len(_parent().entry.conditions) + 1
    assert candidate.strategy.entry.logic == "AND"
    assert plan.preview_new_candidates == 1

"""True two-parent StrategyIR exit crossover with immutable proof and development controls."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from application.gpt_guided_research_service import GPTGuidedResearchService
from core.integrity.hashes import content_hash
from experiments.identity import semantic_strategy_hash
from mutation.engine import MutationOperation, apply_operations
from research.llm.guided_crossover import crossover_exit
from research.llm.guided_research_feedback import check_proposal
from strategy_ir.normalizer import normalize_source
from strategy_ir.schema import StrategyIR
from tests.integrations.test_guided_adaptive_director import _decision

DATA = "data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet"
SOURCE = "strategies/normalized/0a805e67c88e16da-4.json"


def _base():
    return normalize_source(Path(__file__).resolve().parents[2] / SOURCE).strategy


def _parents():
    base = _base()
    a = apply_operations(base, [MutationOperation("SET_PARAMETER", "risk.position_size_pct", 90.0)])
    b = apply_operations(
        base,
        [
            MutationOperation("SET_PARAMETER", "risk.position_size_pct", 75.0),
            MutationOperation(
                "REPLACE_RULE",
                "exit.conditions.0",
                {
                    "enabled": True,
                    "left": "sma_fast",
                    "op": "greater_than",
                    "right": "sma_slow",
                    "value": None,
                },
            ),
        ],
    )
    return a, b


def test_real_strategy_ir_crossover_inherits_primary_risk_and_donor_exit():
    a, b = _parents()
    child, proof = crossover_exit(a, b)
    assert child.risk.position_size_pct == a.risk.position_size_pct == 90.0
    assert child.exit.conditions[0].op == b.exit.conditions[0].op == "greater_than"
    assert b.risk.position_size_pct == 75.0
    assert child.entry == a.entry
    assert len({semantic_strategy_hash(x) for x in (a, b, child)}) == 3
    assert proof["hybrid_semantic_hash"] == semantic_strategy_hash(child)
    with pytest.raises(ValueError, match="CROSSOVER_PARENTS_IDENTICAL"):
        crossover_exit(a, a)
    with pytest.raises(
        ValueError, match="CROSSOVER_NO_SIGNAL_STRUCTURE_DIFFERENCE|CROSSOVER_DONOR_EXIT_UNCHANGED"
    ):
        crossover_exit(
            b,
            apply_operations(
                b, [MutationOperation("SET_PARAMETER", "risk.position_size_pct", 70.0)]
            ),
        )
    broken = apply_operations(
        b, [MutationOperation("SET_PARAMETER", "indicators.sma_fast.period", 10)]
    )
    with pytest.raises(ValueError, match="CROSSOVER_INCOMPATIBLE_INDICATOR_DEPENDENCIES"):
        crossover_exit(a, broken)


def _intent(*ops):
    return {
        "mode": "mixed",
        "parent_ids": ["golden_cross"],
        "rationale": (
            "Explicit risk and donor-exit hypothesis; exact costed fills with both "
            "parents as controls"
        ),
        "operations": list(ops),
    }


def _step(svc, point, intent, mode, parent=None, donor=None):
    decision = _decision(point["research_director_brief"], mode=mode, parent=parent, contrast=donor)
    args = {
        "session_id": point["session_id"],
        "checkpoint_token": point["checkpoint_token"],
        "generation": point["generation"],
        "source_path": SOURCE,
        "intent": intent,
        "research_decision": decision,
    }
    if parent is not None:
        args["research_parent_generation"] = parent
    if donor is not None:
        args["crossover_donor_generation"] = donor
    return svc.submit(args)


def test_real_three_generation_failure_inclusive_crossover_and_both_parent_controls(tmp_path):
    root = Path(__file__).resolve().parents[2]
    service = GPTGuidedResearchService(project_root=root, state_dir=tmp_path / "crossover")
    point = service.start(
        {
            "data_path": DATA,
            "generations": 3,
            "seed": 65291,
            "count": 1,
            "require_execution_change": True,
            "allow_research_parent_inheritance": True,
            "adaptive_research_controller": True,
            "allow_two_parent_crossover": True,
            "benchmark_mode": "QQQ_COSTED_NEXT_OPEN_DEV_V1",
        }
    )
    point = _step(
        service,
        point,
        _intent({"op": "SET_PARAMETER", "path": "risk.position_size_pct", "value": 90.0}),
        "EXPLORE",
    )
    assert point["learning_feedback"]["failed_candidates_included"] == 1
    a_run = point["last_run_id"]
    point = _step(
        service,
        point,
        _intent(
            {"op": "SET_PARAMETER", "path": "risk.position_size_pct", "value": 75.0},
            {
                "op": "REPLACE_RULE",
                "path": "exit.conditions.0",
                "condition": {
                    "enabled": True,
                    "left": "sma_fast",
                    "op": "greater_than",
                    "right": "sma_slow",
                },
            },
        ),
        "DIAGNOSE_FAILURE",
    )
    assert point["learning_feedback"]["failed_candidates_included"] == 2
    b_run = point["last_run_id"]
    # Strict two-parent lineage: G1 (risk 90 + cross exit), G2 (risk 75 + level exit).
    # G3 retains G1 risk/entry and adopts G2's exit rule; no other GPT mutations.
    point = _step(service, point, _intent(), "CONTRAST_PARENTS", parent=1, donor=2)
    assert point["status"] == "COMPLETED" and point["completed_generations"] == 3
    assert point["learning_feedback"]["evaluated_candidates"] == 3
    assert point["controlled_training_memory"]["verified_generations"] == 3
    assert point["orders_enabled"] is False and point["sealed_oos_evaluated"] is False
    report = service.training_control({"session_id": point["session_id"], "generation": 3})
    assert report["training_bars"] < 1508
    assert len(report["comparisons"]) == 1
    assert len(report["crossover_donor_comparisons"]) == 1
    donor = report["crossover_donor_comparisons"][0]
    assert donor["donor_run_id"] == b_run
    assert (
        donor["child_semantic_strategy_hash"] == report["comparisons"][0]["semantic_strategy_hash"]
    )
    assert donor["development_only_not_oos"] is True
    assert donor["donor_fill_count"] > 0 and donor["child_fill_count"] > 0
    with sqlite3.connect(service.db_path) as db:
        rows = db.execute(
            (
                "SELECT proposal_json,proposal_hash,status FROM guided_research_proposals "
                "WHERE session_id=? ORDER BY generation"
            ),
            (point["session_id"],),
        ).fetchall()
    assert len(rows) == 3
    proposal = json.loads(rows[2][0])
    assert rows[2][2] == "COMMITTED" and content_hash(proposal) == rows[2][1]
    assert check_proposal(proposal, expected_hash=rows[2][1])
    assert proposal["parent_run_id"] == a_run
    assert proposal["crossover_proof"]["donor_run_id"] == b_run
    assert proposal["crossover_proof"]["primary_generation"] == 1
    assert proposal["crossover_proof"]["donor_generation"] == 2
    assert proposal["research_director_decision"]["research_mode"] == "CONTRAST_PARENTS"
    assert proposal["candidates"][0]["semantic_strategy_hash"] not in {
        proposal["crossover_proof"]["primary_semantic_hash"],
        proposal["crossover_proof"]["donor_semantic_hash"],
    }
    primary = StrategyIR.model_validate(proposal["parent_strategy_ir"])
    donorir = StrategyIR.model_validate(proposal["crossover_donor_strategy_ir"])
    hybrid = StrategyIR.model_validate(proposal["candidates"][0]["strategy_ir"])
    assert hybrid.risk.position_size_pct == primary.risk.position_size_pct == 90
    assert donorir.risk.position_size_pct == 75
    assert hybrid.exit == donorir.exit
    assert hybrid.entry == primary.entry
    damaged = json.loads(rows[2][0])
    damaged["crossover_proof"]["donor_semantic_hash"] = "0" * 64
    with pytest.raises(ValueError, match="GUIDED_PROPOSAL_HASH_MISMATCH"):
        check_proposal(damaged, expected_hash=rows[2][1])


def test_optin_and_director_consistency_cannot_be_bypassed(tmp_path):
    root = Path(__file__).resolve().parents[2]
    service = GPTGuidedResearchService(project_root=root, state_dir=tmp_path / "no-crossover")
    with pytest.raises(ValueError, match="requires adaptive research"):
        service.start(
            {
                "data_path": DATA,
                "generations": 3,
                "require_execution_change": True,
                "allow_research_parent_inheritance": True,
                "allow_two_parent_crossover": True,
            }
        )

"""P3-1: preregister candidates then compare fair costed evaluations."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.data.contracts import DataZone, MarketDataSet
from research.llm.director import ResearchIntent
from research.llm.fixed_budget_arms import (
    FixedBudgetError,
    build_fixed_budget_manifest,
    read_frozen_manifest,
    score_frozen_budget,
    write_frozen_manifest,
)
from tests.research.test_academic_decision_audit import _fixture


def _gpt(parent):
    return ResearchIntent.model_validate(
        {
            "mode": "structure",
            "parent_ids": [parent.strategy.strategy_id],
            "operations": [
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": {
                        "op": "less_equal",
                        "left": "previous_range_breakout",
                        "value": 0.4,
                    },
                }
            ],
            "rationale": "Previously saved model hypothesis, not a newly called LLM.",
        }
    )


def test_preregistered_three_arms_exactly_equal_and_reproducible(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    manifest = build_fixed_budget_manifest(
        compiled, market, [_gpt(compiled)], seed=771, source_evidence_hash="a" * 64
    )
    assert manifest == build_fixed_budget_manifest(
        compiled, market, [_gpt(compiled)], seed=771, source_evidence_hash="a" * 64
    )
    assert manifest["candidates_per_arm"] == 1
    assert [x["arm"] for x in manifest["candidates"]] == [
        "GPT_HISTORICAL",
        "RANDOM",
        "LOCAL_EVOLUTION",
    ]
    assert len({x["candidate_id"] for x in manifest["candidates"]}) == 3
    assert all(len(x["strategy_hash"]) == 64 for x in manifest["candidates"])
    frozen = tmp_path / "budget-plan.json"
    write_frozen_manifest(frozen, manifest)
    assert read_frozen_manifest(frozen) == manifest
    with pytest.raises(FileExistsError):
        write_frozen_manifest(frozen, manifest)
    scored = score_frozen_budget(compiled, market, read_frozen_manifest(frozen))
    assert scored == score_frozen_budget(compiled, market, read_frozen_manifest(frozen))
    assert scored["candidate_evaluations"] == 3
    assert scored["baseline_evaluations"] == 1
    assert {x["arm"] for x in scored["arms"]} == {"GPT_HISTORICAL", "RANDOM", "LOCAL_EVOLUTION"}
    assert all(x["evaluations"] == 1 for x in scored["arms"])
    assert scored["arm_evaluations_equal"] is True
    assert scored["source_scope"] == "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
    assert scored["automatic_parent_promotion"] is False
    assert scored["statistical_superiority_established"] is False
    assert scored["benchmark"]["independent_oos_approved"] is False
    assert all(x["measured"]["max_drawdown"] >= 0 for x in scored["trials"])
    assert all(0 <= x["measured"]["market_exposure"] <= 1 for x in scored["trials"])
    assert all(x["measured"]["transaction_costs"] >= 0 for x in scored["trials"])
    assert all(type(x["same_fill_trace_as_parent"]) is bool for x in scored["trials"])
    assert all(type(x["same_equity_curve_as_parent"]) is bool for x in scored["trials"])
    assert sum(a["same_fill_trace_as_parent_count"] for a in scored["arms"]) == sum(
        x["same_fill_trace_as_parent"] for x in scored["trials"]
    )


def test_plan_mutation_and_market_tampering_block_scoring(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    manifest = build_fixed_budget_manifest(
        compiled, market, [_gpt(compiled)], seed=771, source_evidence_hash="a" * 64
    )
    file = tmp_path / "frozen.json"
    write_frozen_manifest(file, manifest)
    edited = json.loads(file.read_text())
    edited["candidates"][1]["intent"]["operations"][0]["condition"]["value"] = 0.7
    file.write_text(json.dumps(edited))
    with pytest.raises(FixedBudgetError, match="hash|freeze|integrity"):
        read_frozen_manifest(file)
    with pytest.raises(FixedBudgetError, match="hash|freeze|integrity"):
        score_frozen_budget(compiled, market, edited)
    sealed = MarketDataSet(market.version, DataZone.SEALED_OOS, market.bars)
    with pytest.raises(FixedBudgetError, match="development"):
        build_fixed_budget_manifest(
            compiled, sealed, [_gpt(compiled)], seed=771, source_evidence_hash="a" * 64
        )
    with pytest.raises(FixedBudgetError, match="development"):
        score_frozen_budget(compiled, sealed, manifest)
    modified = replace(compiled, strategy_hash="f" * 64)
    with pytest.raises(FixedBudgetError, match="strategy|parent"):
        score_frozen_budget(modified, market, manifest)


def test_two_candidates_per_arm_and_nonduplication_budget_is_fixed(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    intent = _gpt(compiled)
    second = intent.model_copy(deep=True)
    second.operations = tuple(
        [
            second.operations[0].model_copy(
                update={
                    "condition": second.operations[0].condition.model_copy(update={"value": 0.45})
                }
            )
        ]
    )
    first = build_fixed_budget_manifest(
        compiled, market, [intent, second], seed=11, source_evidence_hash="a" * 64
    )
    assert len(first["candidates"]) == 6
    measured = score_frozen_budget(compiled, market, first)
    assert measured["candidate_evaluations"] == 6
    assert all(x["evaluations"] == 2 for x in measured["arms"])
    with pytest.raises(FixedBudgetError, match="duplicate GPT"):
        build_fixed_budget_manifest(
            compiled, market, [intent, intent], seed=11, source_evidence_hash="a" * 64
        )
    with pytest.raises(FixedBudgetError, match="budget"):
        build_fixed_budget_manifest(compiled, market, [], seed=11, source_evidence_hash="a" * 64)

"""P2 risk rejection evidence is bound to the current planning checkpoint."""

from __future__ import annotations

import json

import pytest

from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash
from research.llm.precommit_rejection_feedback import (
    iter_feedback_adjusted_designs,
    summarize_precommit_rejections,
)

BUDGET = ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=15, min_closed_trades=30)


def _signed_row(ops=None):
    body = {
        "schema": "p2-precommit-child-risk-rejection-v1",
        "dataset_hash": "data",
        "parent_selection_hash": "selection",
        "parent_strategy_hash": "strategy",
        "token_hash": "token",
        "risk_budget": BUDGET.model_dump(mode="json"),
        "request_hash": "req",
        "child_strategy_hash": "child",
        "proposal_operations": ops
        if ops is not None
        else [{"op": "REPLACE_RULE", "path": "exit.conditions.0"}],
        "risk_review": {
            "eligible": False,
            "parent_mdd_pct": 15.95,
            "child_mdd_pct": 37.65,
            "closed_trades": 45,
        },
    }
    return {"review_json": json.dumps(body), "review_hash": content_hash(body)}


def _summarize(rows):
    return summarize_precommit_rejections(
        rows=rows,
        dataset_hash="data",
        parent_selection_hash="selection",
        parent_strategy_hash="strategy",
        token_hash="token",
        budget=BUDGET,
    )


def test_authenticated_feedback_mdd_and_adaptive_order():
    feedback = _summarize([_signed_row()])
    assert feedback["rejection_count"] == 1
    assert feedback["absolute_mdd_failures"] == 1
    assert feedback["relative_mdd_failures"] == 1
    assert feedback["proposed_domain_order"] == ["entry", "exit"]
    exit_only = [{"op": "REPLACE_RULE", "path": "exit.conditions.0"}]
    entry = [{"op": "ADD_RULE", "path": "entry.conditions"}]
    holder = [_summarize([])]
    generator = iter_feedback_adjusted_designs([exit_only, exit_only, entry], holder)
    assert next(generator) == exit_only
    holder[0] = feedback
    assert next(generator) == entry


def test_reject_tampered_record_parent_or_token():
    row = _signed_row()
    altered = dict(row)
    altered["review_json"] = row["review_json"].replace("37.65", "20.0")
    with pytest.raises(ValueError, match="signed risk rejection"):
        _summarize([altered])
    with pytest.raises(ValueError, match="current checkpoint"):
        summarize_precommit_rejections(
            rows=[row],
            dataset_hash="data",
            parent_selection_hash="other",
            parent_strategy_hash="strategy",
            token_hash="token",
            budget=BUDGET,
        )
    with pytest.raises(ValueError, match="current checkpoint"):
        summarize_precommit_rejections(
            rows=[row],
            dataset_hash="data",
            parent_selection_hash="selection",
            parent_strategy_hash="strategy",
            token_hash="new_token",
            budget=BUDGET,
        )


def test_empty_feedback_no_fake_evidence():
    result = _summarize([])
    assert result["rejection_count"] == 0
    assert result["absolute_mdd_failures"] == 0
    assert result["never_relax_thresholds"] is True
    assert result["mode"] == "DETERMINISTIC_SIGNED_EVIDENCE_GUIDANCE_NOT_GPT"

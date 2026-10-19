"""The 30-costed-plan comparison must be reproducible from frozen identities."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.score_t4_equal_plan_comparison import (
    ThreeArmComparisonError,
    validate_and_score,
)

EVIDENCE = (
    Path(__file__).resolve().parents[2] / "docs/operations/evidence/quant-validation-20261020"
)


@pytest.fixture(scope="module")
def inputs() -> tuple[dict, dict, dict, dict]:
    def load(name: str) -> dict:
        return json.loads((EVIDENCE / name).read_text())

    return (
        load("t4-equal-plan-frozen-manifest.json"),
        load("t4-equal-plan-observed-sessions.json"),
        load("t4-connected-chatgpt-10gen.json"),
        load("t4-equal-plan-scored-report.json"),
    )


def test_scored_results_match_frozen_30_candidates_and_mcp_evidence(inputs) -> None:
    frozen, observed, gpt, report = inputs
    assert validate_and_score(frozen, observed, gpt) == report
    assert report["arm_evaluations_equal"]
    assert report["original_plan_evaluations_total"] == 30
    assert report["controlled_s7_trials_total"] == 30
    assert len(report["trials"]) == 30
    assert [a["arm"] for a in report["arm_summaries"]] == ["GPT_RECORDED", "RANDOM", "LOCAL"]
    assert [a["pass_count"] for a in report["arm_summaries"]] == [1, 2, 1]
    assert [a["zero_trade_count"] for a in report["arm_summaries"]] == [0, 2, 0]
    assert report["statistical_model_superiority_established"] is False
    assert report["independent_pit_oos_approved"] is False
    assert report["broker_executable"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "plan",
        "parent",
        "data",
        "evidence",
        "result",
        "gpt_identity",
        "arm_missing",
        "hypothesis",
        "count",
        "order",
    ],
)
def test_tampered_outcome_or_frozen_plan_fails_closed(inputs, mutation) -> None:
    m, o, g, _ = (deepcopy(x) for x in inputs)
    if mutation == "plan":
        m["plans"]["RANDOM"][0]["cases"][0]["min_score"] = 0.9
    elif mutation == "parent":
        o["data"][1]["history"][0]["algorithm_plan"]["plan_id"] = "other_parent"
    elif mutation == "data":
        o["data"][1]["dataset_hash"] = "f" * 64
    elif mutation == "evidence":
        o["data"][2]["history"][3]["previous_evidence_hash"] = "a" * 64
    elif mutation == "result":
        o["data"][0]["history"][0]["metrics"]["max_drawdown"] = -0.3
    elif mutation == "gpt_identity":
        o["data"][0]["session_id"] = "0" * 32
    elif mutation == "arm_missing":
        del o["data"][1]
    elif mutation == "hypothesis":
        o["data"][2]["history"][2]["hypothesis_ids"] = []
    elif mutation == "count":
        o["data"][1]["final_report"]["tested_hypotheses"] = 9
    elif mutation == "order":
        o["data"][1]["orders_enabled"] = True
    with pytest.raises(ThreeArmComparisonError):
        validate_and_score(m, o, g)

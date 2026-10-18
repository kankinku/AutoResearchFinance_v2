"""P0-4: audited signal improvements must not be confused with sizing risk reductions."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from core.integrity.hashes import content_hash
from research.llm.economic_feedback import (
    EconomicFeedbackError,
    build_economic_feedback,
    gate_research_direction,
)
from tests.research.test_economic_feedback_p0 import example


def _mutate(
    history: list,
    reports: dict,
    *,
    added=0,
    removed=0,
    resized=0,
    parent_costs=20.0,
    child_costs=10.0,
    timing=False,
) -> tuple[list, dict]:
    result = deepcopy(reports)
    delta = result[1]["report"]["experiments"][0]["execution_delta"]
    delta.update(
        {
            "added_event_count": added,
            "removed_event_count": removed,
            "resized_event_count": resized,
            "execution_timing_changed": timing,
            "parent_costs": parent_costs,
            "child_costs": child_costs,
        }
    )
    result[1]["record_hash"] = content_hash(
        {k: v for k, v in result[1].items() if k != "record_hash"}
    )
    return history, result


def test_mechanical_position_shrink_is_not_a_profitable_signal_candidate() -> None:
    history, raw = example(child_equity=15000.0, child_fills=64, trade_metric="max_drawdown")
    h, reports = _mutate(history, raw, resized=64)
    reports[1]["report"]["experiments"][0].update(
        parent_metric=0.2, child_metric=0.12,
    )
    reports[1]["record_hash"] = content_hash(
        {k: v for k, v in reports[1].items() if k != "record_hash"}
    )
    out = build_economic_feedback(h, reports, qqq_total_return=1.877724)
    assert out["execution_change_counts"] == {"SIZE_ONLY_CHANGED": 1}
    assert out["outcomes"]["return_better"] == 1
    assert out["signal_review_candidates"] == out["review_candidates"] == []
    assert len(out["mechanical_size_risk_reviews"]) == 1
    trial = out["mechanical_size_risk_reviews"][0]
    assert trial["execution_change_kind"] == "SIZE_ONLY_CHANGED"
    assert out["latest"]["actual_signal_timing_change"] is False
    assert trial["child_minus_qqq_total_return_pp"] == pytest.approx(-137.7724)
    assert out["latest"]["parent_transaction_costs"] == 20.0
    assert out["latest"]["child_transaction_costs"] == 10.0
    assert out["latest"]["child_exposure_verified"] is False
    assert out["latest"]["child_max_drawdown_full_period_verified"] is True
    decision = gate_research_direction(
        {"recommended_mode": "EVOLVE", "completed_generations": 1},
        out,
    )
    assert decision["recommended_mode"] == "TEST_HYPOTHESIS"
    assert decision["reason_code"] == "LATEST_MECHANICAL_SIZING_NOT_SIGNAL_EVOLUTION"
    assert len(h) == 1


def test_true_timing_change_is_reviewable_but_not_promoted_or_oos() -> None:
    h, raw = example(child_equity=13000.0, child_fills=64)
    h, reports = _mutate(h, raw, added=2, removed=3, resized=4)
    out = build_economic_feedback(h, reports, qqq_total_return=1.877724)
    assert out["execution_change_counts"] == {"SIGNAL_TIMING_CHANGED": 1}
    assert len(out["signal_review_candidates"]) == 1
    latest = out["latest"]
    assert latest["actual_signal_timing_change"] is True
    assert latest["added_event_count"] == 2
    assert latest["removed_event_count"] == 3
    assert latest["child_minus_qqq_total_return_pp"] < 0
    assert latest["child_exposure_verified"] is False
    assert latest["better_return_development_windows"] == 4
    assert out["automatic_child_promotion"] is False
    assert out["independent_oos_approved"] is False
    assert (
        gate_research_direction(
            {"recommended_mode": "EVOLVE", "completed_generations": 1},
            out,
        )["recommended_mode"]
        == "EVOLVE"
    )


def test_no_actual_execution_change_cannot_be_a_research_success() -> None:
    h, raw = example(child_equity=14000.0, child_fills=64)
    h, reports = _mutate(h, raw)
    out = build_economic_feedback(h, reports)
    assert out["review_candidates"] == []
    assert out["mechanical_size_risk_reviews"] == []
    assert out["execution_change_counts"] == {"UNCHANGED_EXECUTIONS": 1}
    # The mismatch may be an inherited, contrived record; no structural improvement.
    gate = gate_research_direction(
        {"recommended_mode": "EVOLVE", "completed_generations": 1},
        out,
    )
    assert gate["recommended_mode"] == "EXPLORE"
    assert gate["reason_code"] == "LATEST_CONTROL_NO_SIGNAL_OR_SIZE_CHANGE"


def test_invalid_costs_and_evidence_change_fail_closed() -> None:
    h, raw = example(child_fills=64)
    _, reports = _mutate(h, raw, resized=4, parent_costs=-1.0)
    with pytest.raises(EconomicFeedbackError, match="negative transaction costs"):
        build_economic_feedback(h, reports)
    _, reports = _mutate(h, raw, added=-1)
    with pytest.raises(EconomicFeedbackError, match="invalid execution change count"):
        build_economic_feedback(h, reports)
    with pytest.raises(EconomicFeedbackError, match="QQQ"):
        build_economic_feedback(h, raw, qqq_total_return=float("nan"))
    _, reports = _mutate(h, raw, added=2)
    reports[1]["report"]["experiments"][0]["child_final_equity"] = 9999.0
    with pytest.raises(EconomicFeedbackError, match="integrity mismatch"):
        build_economic_feedback(h, reports)


def test_real_53_generation_s7_reports_read_only_classification() -> None:
    root = Path("/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory")
    src = root / "state/moon-http/research/academic-gpt-checkpoints"
    if not (src / "cycles.sqlite").exists():
        pytest.skip("Pinned Moon 53 generation fixture not present")
    sid = "c1eadd67bad94d7ea182dc274224dbce"
    with (
        sqlite3.connect(f"file:{src / 'cycles.sqlite'}?mode=ro", uri=True) as ca,
        sqlite3.connect(f"file:{src / 'gateway.sqlite'}?mode=ro", uri=True) as ga,
    ):
        h = []
        for _g, encoded, evidence_hash in ca.execute(
            "SELECT generation,evidence_json,evidence_hash FROM generations "
            "WHERE session_id=? ORDER BY generation",
            (sid,),
        ):
            row = json.loads(encoded)
            row["evidence_hash"] = evidence_hash
            h.append(row)
        measured = {}
        for g, raw, digest in ga.execute(
            "SELECT generation,report_json,report_hash FROM experiment_reports "
            "WHERE session_id=? AND generation BETWEEN 4 AND 53",
            (sid,),
        ):
            result = json.loads(raw)
            assert content_hash(result) == digest
            measured[g] = {**result, "record_hash": digest}
        original_gen = ca.execute("SELECT completed FROM sessions WHERE id=?", (sid,)).fetchone()[0]
    assert original_gen == 53
    assert len(h) == 53 and len(measured) == 50
    out = build_economic_feedback(h, measured, qqq_total_return=1.8777241068917014)
    assert out["tested_experiments"] == 50
    assert out["execution_change_counts"]["SIZE_ONLY_CHANGED"] == 29
    assert out["signal_effect_gate"] == "REQUIRES_ADDED_REMOVED_OR_TIMING_CHANGED_FILLS"
    assert (
        len(out["mechanical_size_risk_reviews"]) >= 1
        or out["execution_change_counts"]["SIZE_ONLY_CHANGED"] > 0
    )
    assert all(x["actual_signal_timing_change"] for x in out["signal_review_candidates"])
    assert all(
        x["execution_change_kind"] == "SIZE_ONLY_CHANGED"
        for x in out["mechanical_size_risk_reviews"]
    )
    assert out["qqq_benchmark_scope"] == "COSTED_RAW_QQQ_SAME_REUSED_DEVELOPMENT_ONLY"

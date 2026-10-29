"""A12 supplemental lag repair study; preserve original A11 snapshot as evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.integrity.hashes import content_hash
from scripts import v3_chart_a11_g68_preregistered as a11
from scripts.v3_chart_a12_lag_control_replay import run_a12

ORIGINAL_REPORT = Path("docs/operations/quant-v3-chart-A11-G68-diagnostic-results-20261029.json")
ADDENDUM = Path("docs/operations/quant-v3-chart-A12-lag-control-addendum-20261029.json")


def test_A12_repaired_B4_preserves_original_A11_and_other_five() -> None:
    old = json.loads(ORIGINAL_REPORT.read_text())
    assert old["valid_costed_arm_count"] == 5
    assert old["blocked_arm_count"] == 1
    assert next(x for x in old["candidate_arms"] if x["arm"] == "B4_DELAYED_CONTROL")[
        "status"
    ] == "BLOCKED_DOUBLE_LAG_PROVENANCE"
    needed = ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite")
    if not all((a11.ORIGINAL / f).is_file() for f in needed):
        pytest.skip("G452 independent backup source not available in CI")
    report = run_a12(save=False)
    assert report["scope"] == "A12_SUPPLEMENT_NONPIT_DEVELOPMENT_ONLY"
    assert report["original_A11_result_content_hash"] == old["result_content_hash"]
    assert report["five_preregistered_costed_arms_bitwise_unchanged"] is True
    assert report["new_valid_B4_only"] is True
    assert report["B4"]["research_feature_ref_lag_bars"] == 35
    assert report["B4"]["closed_trades"] == 7
    assert report["B4"]["total_return"] == pytest.approx(-0.039532650472031694)
    assert report["gpt_calls_performed"] == 0
    assert report["new_counted_generations"] == 0
    assert report["independent_OOS_accessed"] is False
    assert report["operating_main_merged"] is False
    assert report["result_content_hash"] == content_hash({
        k: v for k, v in report.items()
        if k not in ("observed_at_kst", "result_content_hash")
    })


def test_A12_saved_addendum_is_reproducible_metadata() -> None:
    saved = json.loads(ADDENDUM.read_text())
    assert saved["B4"]["counted_as_valid_evaluation"] is True
    assert saved["preregistration_hash"] == a11.read_prereg()["freeze_hash"]
    assert saved["original_A11_result_content_hash"] == json.loads(
        ORIGINAL_REPORT.read_text()
    )["result_content_hash"]

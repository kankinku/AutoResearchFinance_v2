"""Strict opt-in S7 quality rejection; old S7 evidence format is untouched."""
from pathlib import Path

import pytest

from research.indicator_engine.controlled_experiments import compare_controlled_experiments
from research.llm.s7_quality_gate_p4_3 import (
    P4S7Rejected,
    assess_p4_s7_quality,
)
from tests.research.test_controlled_academic_experiments import _inputs


def test_identical_fill_trace_is_rejected_before_counting(tmp_path: Path):
    catalog, compiled, market, payload = _inputs(tmp_path)
    result = compare_controlled_experiments(catalog, compiled, market, payload)
    with pytest.raises(P4S7Rejected, match="NO_OBSERVED_EFFECT") as err:
        assess_p4_s7_quality(result)
    assert err.value.reasons[0]["hypothesis_id"] == payload["hypotheses"][0]["hypothesis_id"]
    assert err.value.reasons[0]["reason"] == "NO_OBSERVED_EFFECT"


def test_execution_changed_but_wrong_direction_remains_valid_research(tmp_path: Path):
    catalog, compiled, market, payload = _inputs(tmp_path, op="CHANGE_POSITION_SIZE")
    result = compare_controlled_experiments(catalog, compiled, market, payload)
    quality = assess_p4_s7_quality(result)
    assert quality["eligible"] is True
    assert quality["evidence_hash"] == result.evidence_hash

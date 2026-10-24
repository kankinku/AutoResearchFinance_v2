"""P4-3 consistency of typed S7 metrics and canonical next-open execution exposure."""
from pathlib import Path
from typing import get_args

import pytest

from research.indicator_engine.controlled_experiments import (
    SUPPORTED_CONTROLLED_METRICS,
    compare_controlled_experiments,
)
from research.llm.diagnostic_research import SUPPORTED_S7_METRICS, ExperimentHypothesis
from tests.research.test_controlled_academic_experiments import _inputs


def test_s7_contract_lists_exactly_executable_metrics(tmp_path: Path):
    assert set(SUPPORTED_S7_METRICS) == SUPPORTED_CONTROLLED_METRICS
    assert set(get_args(ExperimentHypothesis.model_fields["expected_metric"].annotation)) == (
        SUPPORTED_CONTROLLED_METRICS
    )
    assert "exposure" in SUPPORTED_S7_METRICS
    assert "win_rate" not in SUPPORTED_S7_METRICS
    assert "profit_factor" not in SUPPORTED_S7_METRICS


def test_s7_exposure_measures_actual_canonical_executed_positions(tmp_path: Path):
    catalog, compiled, market, payload = _inputs(tmp_path, op="CHANGE_POSITION_SIZE")
    payload["hypotheses"][0]["expected_metric"] = "exposure"
    payload["hypotheses"][0]["predicted_direction"] = "DECREASE"
    result = compare_controlled_experiments(catalog, compiled, market, payload)
    outcome = result.experiments[0]
    assert outcome.metric == "exposure"
    assert outcome.parent_metric is not None
    assert outcome.child_metric is not None
    assert 0 <= outcome.parent_metric <= 1
    assert outcome.child_metric == pytest.approx(outcome.parent_metric)
    assert outcome.status == "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY"
    assert result.out_of_sample_approved is False


def test_s7_unsupported_profit_and_win_rate_are_not_offered(tmp_path: Path):
    catalog, compiled, market, payload = _inputs(tmp_path)
    for metric in ("win_rate", "profit_factor"):
        payload["hypotheses"][0]["expected_metric"] = metric
        with pytest.raises(ValueError, match="unsupported"):
            compare_controlled_experiments(catalog, compiled, market, payload)

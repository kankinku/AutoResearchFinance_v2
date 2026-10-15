"""Ensure LLM proposal guidance lists metrics S7 can actually measure."""
from __future__ import annotations


def test_reported_mcp_experiment_metric_choices_equal_supported_s7_metrics():
    from research.indicator_engine.controlled_experiments import (
        SUPPORTED_CONTROLLED_METRICS,
    )
    from research.indicator_engine.experiment_preflight import (
        academic_diagnostic_quality_hint,
    )

    guidance = academic_diagnostic_quality_hint()
    assert set(guidance["supported_controlled_metrics"]) == SUPPORTED_CONTROLLED_METRICS
    assert "win_rate" not in guidance["supported_controlled_metrics"]
    assert "max_drawdown" in guidance["supported_controlled_metrics"]

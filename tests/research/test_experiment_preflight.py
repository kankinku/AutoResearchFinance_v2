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


def test_guidance_promotes_causal_ablation_without_restricting_complex_strategies():
    """Composite strategies remain valid; credit requires isolated controls."""
    from research.indicator_engine.experiment_preflight import (
        academic_diagnostic_quality_hint,
    )

    guidance = academic_diagnostic_quality_hint()
    example = guidance["informative_reviewed_example"]["next_intent"]["operations"]
    assert len(example) == 1
    assert example[0]["path"] == "entry.conditions.0"
    attribution = guidance["causal_attribution_guidance"]
    assert attribution["ablation_design"]["same_parent_for_all"]
    assert attribution["ablation_design"]["separate_entry_only"]
    assert attribution["ablation_design"]["separate_exit_only"]
    assert "Multi-operation experiments are allowed" in attribution["multi_intervention"]
    assert "JOINT" in attribution["multi_intervention"]
    assert attribution["ablation_design"]["label"] == (
        "REUSED_DEVELOPMENT_NOT_INDEPENDENT_CAUSAL_PROOF"
    )

from __future__ import annotations

import pytest

from evaluation.pareto import pareto_frontier
from evaluation.regimes import regime_breakdown
from evaluation.sensitivity import parameter_sensitivity


def test_parameter_sensitivity_reports_stable_interval_and_importance() -> None:
    report = parameter_sensitivity({"fast": {5: 0.10, 6: 0.11, 7: 0.09}})

    assert report.status == "OK"
    assert report.ranges["fast"] == (5.0, 7.0)
    assert report.importance["fast"] >= 0


def test_analysis_tools_preserve_insufficient_evidence() -> None:
    report = parameter_sensitivity({"fast": {5: 0.10}})
    assert report.status == "INSUFFICIENT_EVIDENCE"
    assert report.ranges == {}
    assert regime_breakdown(("bull",), (0.1,)).status == "INSUFFICIENT_EVIDENCE"


def test_regime_breakdown_and_pareto_frontier_are_deterministic() -> None:
    regimes = regime_breakdown(("bull", "bull", "bear"), (0.1, -0.02, 0.03))
    assert regimes.status == "OK"
    assert regimes.by_regime["bull"].count == 2
    assert regimes.by_regime["bear"].mean_return == pytest.approx(0.03)
    frontier = pareto_frontier(
        {"a": (0.8, 0.2), "b": (0.7, 0.1), "c": (0.6, 0.3)}, maximize=(True, False)
    )
    assert frontier == ("a", "b")

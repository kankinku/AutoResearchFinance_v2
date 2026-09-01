from __future__ import annotations

import pytest

from evaluation.attribution import compare_feature_ablation


def test_feature_ablation_reports_marginal_return_contribution() -> None:
    result = compare_feature_ablation(
        "vix_percentile",
        (100.0, 105.0, 110.0),
        (100.0, 102.0, 103.0),
    )

    assert result.with_feature_return == pytest.approx(0.10)
    assert result.without_feature_return == pytest.approx(0.03)
    assert result.marginal_return == pytest.approx(0.07)
    assert result.contributes is True

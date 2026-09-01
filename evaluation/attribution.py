from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureAblation:
    feature_id: str
    with_feature_return: float
    without_feature_return: float
    marginal_return: float
    contributes: bool


def compare_feature_ablation(
    feature_id: str,
    with_feature_equity: Sequence[float],
    without_feature_equity: Sequence[float],
) -> FeatureAblation:
    if not feature_id:
        raise ValueError("feature_id cannot be empty")
    if not with_feature_equity or not without_feature_equity:
        raise ValueError("equity curves cannot be empty")
    with_return = with_feature_equity[-1] / with_feature_equity[0] - 1.0
    without_return = without_feature_equity[-1] / without_feature_equity[0] - 1.0
    marginal = with_return - without_return
    return FeatureAblation(feature_id, with_return, without_return, marginal, marginal > 0)

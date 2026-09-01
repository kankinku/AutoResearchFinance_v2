from __future__ import annotations

from core.features.registry import default_feature_registry


def test_default_feature_catalog_exposes_optional_macro_candidates() -> None:
    names = default_feature_registry().names()

    assert "vix_percentile" in names
    assert "gold_returns" in names
    assert "dxy_returns" in names
    assert "us_2y_change" in names
    assert "us_10y_change" in names
    assert "japan_2y_change" in names
    assert "korea_10y_change" in names
    assert "qqq_returns" in names
    assert "nasdaq_returns" in names

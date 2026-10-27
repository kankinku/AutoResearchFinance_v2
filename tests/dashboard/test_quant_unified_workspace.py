"""The canonical Quant homepage is a SINGLE app with 3 research-oriented modes."""

from __future__ import annotations

import pytest

from scripts import quant_chart_lab_bridge as bridge
from scripts.quant_unified_workspace import compose_unified_workspace


def test_all_three_tabs_share_exactly_one_dom_without_iframe() -> None:
    html = bridge.chart_page(main=True).decode()
    for id_ in (
        "quant-panel-development",
        "quant-panel-oos",
        "quant-panel-operations",
        "quant-tab-development",
        "quant-tab-oos",
        "quant-tab-operations",
        "trade-visualization",
        "oos-price",
        "oos-equity",
        "quant-metric-dev",
        "quant-metric-oos",
        "quant-metric-qqq",
    ):
        assert html.count('id="' + id_ + '"') == 1
    assert "<iframe" not in html
    assert 'data-quant-tab="oos"' in html
    assert 'data-quant-tab="operations"' in html
    assert 'id="quant-panel-oos" role="tabpanel"' in html
    assert 'id="quant-panel-operations" role="tabpanel"' in html
    assert html.count('data-quant-period="90"') == 2
    assert "quant-unified.js?v=u1" in html
    assert "quant-oos-2026.js?v=u1" in html
    assert 'href="research"' in html
    assert "독립 OOS 검증 및 실거래는 포함되지 않습니다" in html
    assert "G124 한 개" in html


def test_legacy_chart_and_oos_are_still_independently_loadable() -> None:
    legacy = bridge.chart_page().decode()
    assert "quant-panel-oos" not in legacy
    assert "quant-unified.js" not in legacy
    assert 'id="trade-visualization"' in legacy


def test_strict_allowlist_for_all_unified_assets() -> None:
    for asset in (
        "quant-unified.js",
        "quant-unified.css",
        "quant-oos-2026.js",
        "quant-oos-2026.css",
    ):
        source = bridge.chart_asset(asset)
        assert source is not None and len(source[1]) > 100
        assert source[0].startswith("text/")
    assert bridge.chart_asset("../../.env") is None
    assert bridge.chart_asset("quant-unified.py") is None


def test_layout_composition_rejects_changed_source_layout() -> None:
    with pytest.raises(ValueError, match="development chart markup"):
        compose_unified_workspace("<html><main></main><main></main></html>")


def test_canonical_chart_home_uses_original_provenance_only() -> None:
    html = bridge.chart_page(main=True).decode()
    assert html.index('id="trade-visualization"') < html.index('id="quant-panel-oos"')
    unified_script = bridge.chart_asset("quant-unified.js")
    assert unified_script is not None
    assert "2026년은 G124만 사후 평가됨" in unified_script[1].decode()
    assert "2026년 가격" in html

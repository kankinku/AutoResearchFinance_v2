from pathlib import Path

STATIC = Path(__file__).parents[2] / "dashboard" / "static"


def test_backtest_dashboard_has_user_friendly_generation_explorer() -> None:
    html = (STATIC / "backtest.html").read_text(encoding="utf-8")
    javascript = (STATIC / "backtest.js").read_text(encoding="utf-8")

    for marker in (
        "빠른 보기",
        "최근 세대",
        "최고 점수",
        "QQQ 대비 우수",
        "위험 준수",
        "세대 검색",
        "성과 기준",
        "검색 결과",
        "사용 설명",
        "scroll-table",
        "cagr-chart",
    ):
        assert marker in html
    for marker in (
        "generation-search",
        "generation-status-filter",
        "generation-sort",
        "quick-filter",
        "filteredGenerations",
        "renderGenerationExplorer",
    ):
        assert marker in javascript


def test_backtest_dashboard_keeps_technical_identifiers_out_of_primary_explorer() -> None:
    html = (STATIC / "backtest.html").read_text(encoding="utf-8")
    explorer_start = html.index('class="generation-explorer"')
    explorer_end = html.index('id="generation-summary-table"')
    explorer = html[explorer_start:explorer_end]
    assert "실행 ID" not in explorer
    assert "전략 해시" not in explorer
    assert "상세 진단" in html


def test_backtest_dashboard_uses_scrollable_regions_instead_of_long_page_lists() -> None:
    html = (STATIC / "backtest.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    javascript = (STATIC / "backtest.js").read_text(encoding="utf-8")

    assert html.count('class="table-wrap scroll-table') >= 3
    assert "max-height" in css
    assert "overflow-y:auto" in css
    assert "chart-bar-stack" in javascript

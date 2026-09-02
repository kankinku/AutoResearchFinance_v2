from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).parents[2] / "dashboard" / "static"


def test_dashboard_assets_are_local_and_contain_required_sections() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC / "app.js").read_text(encoding="utf-8")

    for marker in (
        "모의투자 전용",
        "현재 상황",
        "주의 필요",
        "다음 행동",
        "연구 현황",
        "최근 평가",
        "상세 분석",
        "새로고침",
        "aria-live",
        "계좌 상세",
        "인디케이터 카탈로그",
        "copy-command",
        "프론티어 전략",
    ):
        assert marker in html
    assert "사용 방법" not in html
    assert "<details" in html
    assert "dashboard-refresh" not in html
    assert "integrations.codex_mcp_server" not in html
    assert "research-intent" not in html
    assert html.count('id="system-status"') == 1
    assert html.count('id="champion-score"') == 1
    assert "https://" not in html
    assert "http://" not in html
    assert "fetch(\"/api/dashboard\")" in javascript
    assert "fetch(\"/api/health\")" in javascript
    assert "fetch(\"/api/refresh\"" in javascript
    assert "fetch(\"/api/features/catalog\")" in javascript
    assert "renderFeatureCatalog" in javascript
    assert "escapeHtml" in javascript
    assert "textContent" in javascript
    assert "navigator.clipboard.writeText" in javascript
    assert "statusLabel" in javascript
    assert "모의투자" in javascript
    assert "How to use" not in html
    assert "Paper Operations Dashboard" not in html
    assert "Refresh" not in html


def test_dashboard_has_no_remote_asset_dependency() -> None:
    for asset in STATIC.iterdir():
        if asset.is_file():
            content = asset.read_text(encoding="utf-8")
            assert "cdn." not in content
            assert "http://" not in content
            assert "https://" not in content


def test_backtest_page_is_separate_and_connects_to_backtest_api() -> None:
    html = (STATIC / "backtest.html").read_text(encoding="utf-8")
    javascript = (STATIC / "backtest.js").read_text(encoding="utf-8")
    research_html = (STATIC / "index.html").read_text(encoding="utf-8")

    for marker in (
        "백테스트 관리",
        "실행 원장",
        "선택 결과",
        "검증된 전략 실행",
        "실행 명령 복사",
        "성과 곡선",
        "연구 운영",
        "aria-live",
    ):
        assert marker in html
    assert 'href="/backtest"' in research_html
    assert 'href="/"' in html
    assert 'fetch("/api/backtest")' in javascript
    assert "/api/backtest/runs/" in javascript
    assert "navigator.clipboard.writeText" in javascript
    assert "escapeHtml" in javascript
    assert "https://" not in html

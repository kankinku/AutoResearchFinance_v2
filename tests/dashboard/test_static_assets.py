from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).parents[2] / "dashboard" / "static"


def test_dashboard_assets_are_local_and_contain_required_sections() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC / "app.js").read_text(encoding="utf-8")

    for marker in (
        "모의투자 전용",
        "계좌",
        "테스트 기록",
        "최고 전략",
        "전략 발전",
        "병렬 작업",
        "새로고침",
        "aria-live",
        "사용 방법",
        "<details",
        "<summary",
        "열기",
        "dashboard-refresh",
        "integrations.codex_mcp_server",
        "research-intent",
        "copy-command",
    ):
        assert marker in html
    assert "https://" not in html
    assert "http://" not in html
    assert "fetch(\"/api/dashboard\")" in javascript
    assert "fetch(\"/api/health\")" in javascript
    assert "fetch(\"/api/refresh\"" in javascript
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

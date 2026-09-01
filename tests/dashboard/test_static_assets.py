from __future__ import annotations

from pathlib import Path


STATIC = Path(__file__).parents[2] / "dashboard" / "static"


def test_dashboard_assets_are_local_and_contain_required_sections() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC / "app.js").read_text(encoding="utf-8")

    for marker in (
        "PAPER ONLY",
        "Account",
        "Test History",
        "Champion Strategy",
        "Strategy Progress",
        "Parallel Workers",
        "Refresh",
        "aria-live",
    ):
        assert marker in html
    assert "https://" not in html
    assert "http://" not in html
    assert "fetch(\"/api/dashboard\")" in javascript
    assert "fetch(\"/api/health\")" in javascript
    assert "fetch(\"/api/refresh\"" in javascript
    assert "escapeHtml" in javascript
    assert "textContent" in javascript


def test_dashboard_has_no_remote_asset_dependency() -> None:
    for asset in STATIC.iterdir():
        if asset.is_file():
            content = asset.read_text(encoding="utf-8")
            assert "cdn." not in content
            assert "http://" not in content
            assert "https://" not in content

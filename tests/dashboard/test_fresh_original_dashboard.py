"""Checks that the user's original dashboard UI is served without altering it."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from dashboard.contracts import BacktestSnapshot, DashboardSnapshot
from scripts import fresh_original_dashboard as original
from scripts.fresh_research_dashboard import snapshot


def test_original_design_files_unchanged_and_nested_navigation() -> None:
    source = Path("dashboard/static/index.html").read_text(encoding="utf-8")
    assert "연구 운영" in source
    html = original.page("index.html").decode()
    backtest = original.page("backtest.html").decode()
    assert 'href="static/styles.css"' in html
    assert 'href="backtest"' in html
    assert 'src="static/app.js"' in html
    assert 'href="static/styles.css?v=20260903"' in backtest
    assert "백테스트" in backtest
    for name in ("app.js", "backtest.js"):
        js = original.script(name).decode()
        assert '/api/' not in js
        assert 'fetch(' in js


def test_readonly_sqlite_bridge_matches_original_contracts() -> None:
    research = snapshot()
    dashboard = original.compat(research)
    detail = original.backtest(research, dashboard)
    DashboardSnapshot.model_validate(dashboard)
    BacktestSnapshot.model_validate(detail)
    assert detail["research"]["completed_generations"] == research["completed"]
    assert detail["research"]["requested_generations"] == research["requested"]
    assert len(detail["generations"]) == research["completed"]
    assert len(dashboard["tests"]) == research["completed"]
    assert not dashboard["mode"]["live_enabled"]
    assert "NON_PIT_DEVELOPMENT_ONLY" in dashboard["warning_codes"]
    assert detail["summary"]["passing_generation_count"] == 0


def test_readonly_http_bridge_serves_existing_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    base_view = snapshot()
    monkeypatch.setattr(original, "snapshot", lambda: base_view)
    server = ThreadingHTTPServer(("127.0.0.1", 0), original.OriginalDashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = "http://127.0.0.1:" + str(server.server_port)
    try:
        for uri in ("/", "/backtest", "/static/styles.css", "/static/app.js",
                    "/static/backtest.js", "/api/dashboard", "/api/backtest",
                    "/api/features/catalog", "/api/strategies/catalog"):
            with urllib.request.urlopen(url + uri) as response:
                assert response.status == 200
                assert response.read()
        with urllib.request.urlopen(url + "/api/backtest/runs/fresh-G2") as response:
            assert json.load(response)["generation"] == 2
        req = urllib.request.Request(
            url + "/api/refresh", method="POST", data=b""
        )
        with urllib.request.urlopen(req) as response:
            assert response.status == 200
            assert json.load(response)["tests"]
        req = urllib.request.Request(
            url + "/api/backtest", method="POST", data=b""
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 405
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url + "/state/moon-http/secrets")
        assert exc.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

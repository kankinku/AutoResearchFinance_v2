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
    assert html.index('id="performance-title"') < html.index('id="safety-banner"')
    assert html.index('id="perf-best-return"') < html.index('id="runtime-title"')
    assert 'id="perf-return-chart"' in html
    assert 'id="perf-risk-chart"' in html
    assert 'id="perf-progress"' in html
    assert 'id="connection-toggle"' in html
    assert 'id="connection-dialog"' in html
    assert '<details class="operations-collapse">' in html
    assert 'class="performance-priority"' in html
    assert 'href="static/fresh-performance.css"' in html
    assert 'src="static/fresh-performance.js"' in html
    assert 'src="static/app.js"' in html
    assert 'href="static/styles.css?v=20260903"' in backtest
    assert "백테스트" in backtest
    for name in ("app.js", "backtest.js"):
        js = original.script(name).decode()
        assert '/api/' not in js
        assert 'fetch(' in js
    js = original.script("app.js").decode()
    assert 'fetch("api/dashboard")' in js
    assert 'method: "POST"' not in js
    perf = (Path("dashboard/static/fresh-performance.js")).read_text()
    assert 'fetch("api/status"' in perf
    assert "renderReturns(data,subset)" in perf
    assert 'setInterval(refresh,5000)' in perf
    assert 'dialog.showModal()' in perf


def test_readonly_sqlite_bridge_matches_original_contracts() -> None:
    research = snapshot()
    dashboard = original.compat(research)
    detail = original.backtest(research, dashboard)
    DashboardSnapshot.model_validate(dashboard)
    BacktestSnapshot.model_validate(detail)
    assert research["additional_completed"] == max(0,research["completed"]-52)
    assert research["additional_target"] == max(0,research["requested"]-52)
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
                    "/static/fresh-performance.css", "/static/fresh-performance.js",
                    "/static/backtest.js", "/api/status", "/api/dashboard", "/api/backtest",
                    "/api/features/catalog", "/api/strategies/catalog"):
            with urllib.request.urlopen(url + uri) as response:
                assert response.status == 200
                csp=response.headers["Content-Security-Policy"]
                assert "style-src 'self' 'unsafe-inline'" in csp
                assert "script-src 'self'" in csp
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

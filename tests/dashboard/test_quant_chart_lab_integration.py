"""D1-D3: existing authenticated dashboard + audit-only Lab chart integration."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import pytest

from scripts import fresh_original_dashboard as original
from scripts import quant_chart_lab_bridge as bridge


@pytest.fixture()
def connected_chart_dashboard() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), original.OriginalDashboardHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def get(base: str, route: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(base + route, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_chart_page_is_inside_existing_dashboard_navigation() -> None:
    home = original.page("index.html").decode("utf-8")
    backtest = original.page("backtest.html").decode("utf-8")
    chart = bridge.chart_page().decode("utf-8")
    assert 'href="chart">검증 매매 차트</a>' in home
    assert 'href="chart">검증 매매 차트</a>' in backtest
    assert 'href="chart">매매 차트</a>' in chart
    assert 'href="./"' in chart
    assert 'href="backtest"' in chart
    assert 'src="chart-assets/backtest-chart.js?v=p3"' in chart
    assert 'src="chart-assets/vendor/lightweight-charts-5.2.1.standalone.production.js"' in chart
    assert "독립 OOS 검증 및 실거래는 포함되지 않습니다" in chart
    assert 'src="/static/' not in chart
    assert 'href="/static/' not in chart


def test_chart_assets_are_vendored_and_never_call_other_apis() -> None:
    for path in bridge.ASSETS:
        result = bridge.chart_asset(path)
        assert result is not None
        mime, content = result
        assert content and len(content) < 4 * 1024 * 1024
        assert mime.startswith(("text/css", "text/javascript"))
        if path in ("backtest.js", "backtest-chart.js", "backtest-history.js"):
            assert b"/api/backtest" not in content
            assert b"api/chart/backtest" in content
    assert bridge.chart_asset("../../../../etc/passwd") is None
    assert bridge.chart_asset("app.js") is None
    assert bridge.chart_asset("secrets.json") is None


def test_strict_proxy_allowlist_and_no_arbitrary_paths() -> None:
    good = [
        "/api/chart/backtest",
        "/api/chart/backtest/original-lineage",
        "/api/chart/backtest/runs/LAB_REPLAY_14626d55_G094/verification",
        "/api/chart/backtest/runs/LAB_REPLAY_14626d55_G094/candles?offset=0&limit=500",
        "/api/chart/backtest/compare?run_a=LAB_REPLAY_14626d55_G094&run_b=LAB_REPLAY_14626d55_G146",
    ]
    for path in good:
        assert bridge._validated_target(path).startswith("/api/backtest")
    bad = [
        "/api/dashboard",
        "/api/chart/backtest/../../token",
        "/api/chart/backtest/runs/%2e%2e/analysis",
        "/api/chart/backtest/runs/foo/../../account",
        "/api/chart/backtest/runs/run/candles?offset=-1",
        "/api/chart/backtest/runs/run/candles?offset=1&offset=2",
        "/api/chart/backtest/runs/run/candles?api_key=test",
        "/api/chart/backtest/compare?run_a=abc&run_b=../private",
        "/api/chart/backtest/compare?run_a=abc",
        "/api/chart/backtest/runs/run/trades",
        "/api/chart/backtest/refresh",
        "/api/chart/backtest/runs/foo/verification?token=secret",
    ]
    for path in bad:
        with pytest.raises(ValueError):
            bridge._validated_target(path)


def test_real_48_run_audit_api_with_original_dashboard(
    connected_chart_dashboard: str,
) -> None:
    base = connected_chart_dashboard
    status, home = get(base, "/")
    assert status == 200 and b"chart" in home
    status, chart = get(base, "/chart")
    assert status == 200 and b"chart-assets" in chart
    status, original_data = get(base, "/api/backtest")
    assert status == 200
    original_summary = json.loads(original_data)
    assert original_summary["mode"]["live_enabled"] is False
    status, details = get(base, "/api/chart/backtest")
    assert status == 200
    data = json.loads(details)
    assert len(data["runs"]) == 48
    status, original_lineage = get(base, "/api/chart/backtest/original-lineage")
    assert status == 200
    lineage = json.loads(original_lineage)
    assert lineage["verified_count"] == 48
    assert lineage["historical_completed"] == 146
    assert lineage["historical_trace"] is False
    chosen = "LAB_REPLAY_14626d55_G094"
    status, proof_data = get(base, f"/api/chart/backtest/runs/{chosen}/verification")
    assert status == 200
    proof = json.loads(proof_data)
    assert proof["status"] == "VERIFIED"
    status, bars_data = get(base, f"/api/chart/backtest/runs/{chosen}/candles?offset=0&limit=500")
    assert status == 200
    bars = json.loads(bars_data)
    assert bars["total"] == 1508
    status, compare_data = get(
        base,
        "/api/chart/backtest/compare?run_a=LAB_REPLAY_14626d55_G094&run_b=LAB_REPLAY_14626d55_G146",
    )
    assert status == 200
    assert json.loads(compare_data)["status"] == "COMPARABLE"
    for file in ("styles.css", "backtest-chart.js", "backtest.js"):
        status, content = get(base, "/chart-assets/" + file)
        assert status == 200 and len(content) > 100
    for path in ("/chart-assets/../../etc/passwd", "/api/chart/backtest/refresh"):
        assert get(base, path)[0] in (400, 404)


def test_chart_failure_does_not_break_existing_research(
    connected_chart_dashboard: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bridge, "LAB_SERVICE", "http://127.0.0.1:65533")
    base = connected_chart_dashboard
    status, message = get(base, "/api/chart/backtest")
    assert status == 503
    assert b"CHART_OFFLINE" in message
    status, legacy = get(base, "/api/dashboard")
    assert status == 200
    assert json.loads(legacy)["mode"]["live_enabled"] is False
    req = urllib.request.Request(base + "/api/chart/backtest", method="POST", data=b"")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(req, timeout=5)
    assert error.value.code == 405

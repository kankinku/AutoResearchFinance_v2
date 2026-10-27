"""Regression for independent retrospective 2026 chart, not sealed OOS."""

from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts import fresh_original_dashboard as original
from scripts import quant_chart_lab_bridge as assets
from scripts import quant_chart_oos_bridge as oos


@pytest.fixture()
def http_chart() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), original.OriginalDashboardHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def get(base: str, path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=15) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_immutable_2026_oos_provenance_and_metrics() -> None:
    result = oos.evidence()
    assert result["status"] == "VERIFIED_RETROSPECTIVE_NON_PIT_NOT_SEALED"
    assert result["generation"] == 124
    assert result["orders_enabled"] is False
    assert result["period_start"] == "2026-01-02"
    assert result["period_end"] == "2026-10-26"
    assert len(result["candles"]) == len(result["equity"]) == 205
    assert len(result["fills"]) == 20
    assert round(result["metrics"]["strategy_return_pct"], 1) == -5.2
    assert round(result["metrics"]["qqq_return_pct"], 1) == 14.8
    assert result["metrics"]["qqq_excess_pp"] < -20.0
    assert "2026_FORCED_FLAT_AT_ENTRY" in result["metric_basis"]


def test_same_origin_oos_page_and_evidence_get(http_chart: str) -> None:
    for path in ("/", "/research", "/oos", "/chart", "/api/dashboard"):
        status, body = get(http_chart, path)
        assert status == 200 and body
    status, page = get(http_chart, "/oos")
    assert status == 200 and b"quant-oos-2026.js" in page
    assert b"oos-start" in page and b"oos-end" in page
    assert b"<strong>" in page
    status, json_data = get(http_chart, "/api/oos/2026-g124")
    assert status == 200
    result = json.loads(json_data)
    assert result["status"] == "VERIFIED_RETROSPECTIVE_NON_PIT_NOT_SEALED"
    assert result["metrics"]["fill_count"] == 20
    assert result["orders_enabled"] is False
    status, home = get(http_chart, "/")
    assert status == 200 and b'data-quant-tab="oos"' in home


def test_oos_frontend_static_assets_allowlist() -> None:
    for path in ("quant-oos-2026.js", "quant-oos-2026.css"):
        checked = assets.chart_asset(path)
        assert checked is not None and checked[1]
    assert assets.chart_asset("../../secrets") is None
    assert b"api/oos/2026-g124" in assets.chart_asset("quant-oos-2026.js")[1]


def test_source_mutation_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, http_chart: str
) -> None:
    destination = tmp_path / "altered"
    shutil.copytree(oos.RESULT, destination)
    data = json.loads((destination / "2026_forward_equity.json").read_text())
    data[-1]["equity"] = data[-1]["equity"] + 1200
    (destination / "2026_forward_equity.json").write_text(json.dumps(data))
    monkeypatch.setattr(oos, "RESULT", destination)
    with pytest.raises(ValueError, match="forward orders and mark-to-market proofs diverged"):
        oos.evidence()
    status, response = get(http_chart, "/api/oos/2026-g124")
    assert status == 503
    assert json.loads(response)["error"] == "OOS_EVIDENCE_UNAVAILABLE"
    # Original Quant research metrics remain available even on OOS failure.
    assert get(http_chart, "/api/dashboard")[0] == 200

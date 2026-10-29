"""A15: a bounded real-P9 integration proof, not a fabricated Lab fixture.

The isolated original 48-run, 146-generation DEVELOPMENT evidence is read
through the Lab's own GET-only loopback preview. No main server, research
workers, orders, independent OOS or session state are started or modified.
"""
from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts import fresh_original_dashboard as original
from scripts import quant_chart_lab_bridge as bridge

LAB = Path("/shared/moon-workspace/Quant-Backtest-Lab-20261027")
P9 = LAB / "state/lab-p9-original-G132-G146-20261027/preview"
PYTHON = LAB / ".venv/bin/python"
HOST = "127.0.0.1"


def _get(url: str) -> tuple[int, dict[str, object]]:
    with urllib.request.urlopen(url, timeout=12) as response:
        assert response.headers.get("Content-Type", "").startswith("application/json")
        data = json.load(response)
        assert isinstance(data, dict)
        return response.status, data


@pytest.fixture()  # type: ignore[untyped-decorator]  # pytest in this venv has untyped stubs
def isolated_original_p9_lab(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    if not PYTHON.is_file() or not P9.is_dir():
        pytest.skip("verified read-only P9 Lab is not installed on this CI host")

    # P9 is an immutable, separately owned verified-development snapshot.
    # Do not infer a replacement from arbitrary state dirs.
    root = LAB.resolve(strict=True)
    safe = P9.resolve(strict=True)
    if safe != root / "state/lab-p9-original-G132-G146-20261027/preview":
        pytest.fail("P9 snapshot escaped its approved original source path")
    required = ("test-records.jsonl", "verified_lineage_manifest.json",
                "original_session_history.json")
    if any(not (P9 / name).is_file() for name in required):
        pytest.fail("installed P9 proof is partial; cannot assert 48 verified replays")
    if any(item.is_symlink() for item in P9.rglob("*")):
        pytest.fail("P9 snapshot must not contain filesystem symlinks")

    with socket.socket() as probe:
        probe.bind((HOST, 0))
        port = probe.getsockname()[1]
    url = f"http://{HOST}:{port}"
    command = [
        str(PYTHON), "-m", "scripts.run_backtest_lab_preview",
        "--state-dir", str(P9), "--host", HOST, "--port", str(port),
    ]
    # A child process isolated from the global supervisor. It only reads P9;
    # the checked Lab preview explicitly blocks state outside Lab/state,
    # non-GET verbs, private routes and non-loopback binding.
    child = subprocess.Popen(
        command, cwd=LAB, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(65):
            if child.poll() is not None:
                pytest.fail("local P9 Lab preview exited before the readiness check")
            try:
                status, body = _get(url + "/api/backtest")
                if status == 200:
                    observed_runs = body.get("runs")
                    assert isinstance(observed_runs, list) and len(observed_runs) == 48
                    break
            except (OSError, ValueError, KeyError):
                time.sleep(0.2)
        else:
            pytest.fail("read-only P9 Lab preview did not become ready")
        monkeypatch.setattr(bridge, "LAB_SERVICE", url)
        yield url
    finally:
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=6)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=3)


def test_real_p9_48_verified_runs_end_to_end(
    isolated_original_p9_lab: str,
) -> None:
    upstream = isolated_original_p9_lab
    status, upstream_data = _get(upstream + "/api/backtest")
    assert status == 200
    upstream_runs = upstream_data.get("runs")
    assert isinstance(upstream_runs, list) and len(upstream_runs) == 48
    assert _get(upstream + "/api/backtest/original-lineage")[1]["verified_count"] == 48

    server = ThreadingHTTPServer((HOST, 0), original.OriginalDashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{HOST}:{server.server_port}"
    try:
        for route in ("/", "/chart"):
            with urllib.request.urlopen(base + route, timeout=12) as resp:
                assert resp.status == 200
                assert b"chart-assets" in resp.read()
        _, data = _get(base + "/api/chart/backtest")
        proxied_runs = data.get("runs")
        assert isinstance(proxied_runs, list) and len(proxied_runs) == 48
        _, lineage = _get(base + "/api/chart/backtest/original-lineage")
        assert lineage["verified_count"] == 48
        assert lineage["historical_completed"] == 146
        assert lineage["historical_trace"] is False

        ident = "LAB_REPLAY_14626d55_G094"
        _, detail = _get(
            base + "/api/chart/backtest/runs/" + ident + "/verification"
        )
        assert detail["status"] == "VERIFIED"
        _, candles = _get(
            base + "/api/chart/backtest/runs/" + ident
            + "/candles?offset=0&limit=500"
        )
        assert candles["total"] == 1508
        _, comparison = _get(
            base + "/api/chart/backtest/compare"
            + "?run_a=LAB_REPLAY_14626d55_G094&run_b=LAB_REPLAY_14626d55_G146"
        )
        assert comparison["status"] == "COMPARABLE"
        with urllib.request.urlopen(base + "/chart-assets/backtest-chart.js", timeout=12) as resp:
            assert resp.status == 200 and len(resp.read()) > 1000
        request = urllib.request.Request(base + "/api/chart/backtest", method="POST", data=b"")
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(request, timeout=8)
        assert denied.value.code == 405
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(
                base + "/api/chart/backtest/runs/../secrets", timeout=8
            )
        assert denied.value.code in (400, 404)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=4)

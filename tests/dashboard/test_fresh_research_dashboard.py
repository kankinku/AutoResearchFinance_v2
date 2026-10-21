"""Read-only fresh academic dashboard uses canonical source records, never writes."""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts import fresh_research_dashboard as dash


def _fixture(tmp_path: Path, *, corrupt: bool = False) -> Path:
    root = tmp_path / "fresh"
    data = root / "research/academic-gpt-checkpoints"
    data.mkdir(parents=True)
    sid = "1" * 32
    (root / "session-id.txt").write_text(sid + "\n")
    with sqlite3.connect(data / "cycles.sqlite") as db:
        db.execute(
            "CREATE TABLE sessions (id TEXT,requested INTEGER,completed INTEGER,"
            "status TEXT,dataset_hash TEXT)"
        )
        db.execute(
            "CREATE TABLE generations (session_id TEXT,generation INTEGER,"
            "evidence_json TEXT,evidence_hash TEXT)"
        )
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?)",
                   (sid, 12, 2, "AWAITING_PROVIDER", "c" * 64))
        for i in (1, 2):
            evidence = "a" * 64 if i == 1 else "b" * 64
            obj = {
                "metrics": {
                    "total_return": 0.1 * i,
                    "cagr":0.01*i,
                    "max_drawdown": 0.05 * i,
                    "trade_count": 45 if i == 2 else 10,
                    "exposure": 0.3,
                    "sharpe": 1.2,
                },
                "previous_evidence_hash": None if i == 1 else (
                    "z" * 64 if corrupt else "a" * 64
                ),
            }
            db.execute("INSERT INTO generations VALUES (?,?,?,?)",
                       (sid, i, json.dumps(obj), evidence))
    with sqlite3.connect(data / "gateway.sqlite") as db:
        db.execute("CREATE TABLE stages (session_id TEXT, phase TEXT)")
        db.execute(
            "CREATE TABLE generation_timings (session_id TEXT,generation INTEGER,"
            "start_utc TEXT,end_utc TEXT)"
        )
        db.execute("INSERT INTO stages VALUES (?,?)", (sid, "AWAITING_PLAN"))
        db.execute("INSERT INTO generation_timings VALUES (?,?,?,?)", (
            sid, 1, "2026-10-20T00:00:00+00:00", "2026-10-20T00:01:30+00:00"))
    return root


def test_snapshot_reads_live_sqlite_and_30_trade_eligibility(tmp_path: Path) -> None:
    state = _fixture(tmp_path)
    a = dash.snapshot(state)
    assert a["completed"] == 2
    assert a["requested"] == 12
    assert a["proof_chain_ok"] is True
    assert a["last"]["generation"] == 2
    assert a["best_eligible"]["generation"] == 2
    assert a["best_eligible"]["trades"] == 45
    assert a["avg_generation_seconds"] == 90.0
    assert a["generations"][1]["cagr"]==0.02
    assert 0.18<a["qqq_dev_bh_cagr"]<0.20
    assert a["orders_enabled"] is False
    assert a["model_autonomy_verified"] is False
    assert a["generations"][0]["eligible"] is False
    assert a["generations"][1]["eligible"] is True
    # A read-only dashboard never creates -wal or -shm as a side effect.
    assert sorted(p.name for p in (
        state / "research/academic-gpt-checkpoints"
    ).iterdir()) == ["cycles.sqlite", "gateway.sqlite"]


def test_snapshot_surfaces_broken_evidence_chain(tmp_path: Path) -> None:
    a = dash.snapshot(_fixture(tmp_path, corrupt=True))
    assert a["proof_chain_ok"] is False


def test_missing_db_fails_closed_without_creating_it(tmp_path: Path) -> None:
    state = _fixture(tmp_path)
    target = state / "research/academic-gpt-checkpoints/cycles.sqlite"
    target.unlink()
    with pytest.raises(FileNotFoundError):
        dash.snapshot(state)
    assert not target.exists()


def test_http_routes_security_headers_and_unknown_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dash, "snapshot", lambda: {"completed": 42, "requested": 52})
    server = ThreadingHTTPServer(("127.0.0.1", 0), dash.DashboardHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = "http://127.0.0.1:" + str(server.server_port)
    try:
        with urllib.request.urlopen(base + "/api/status") as response:
            assert response.status == 200
            assert json.load(response)["completed"] == 42
            assert response.headers["Cache-Control"].startswith("no-store")
            assert response.headers["X-Frame-Options"] == "DENY"
        with urllib.request.urlopen(base + "/") as response:
            assert response.status == 200
            assert "Quant AutoResearch" in response.read().decode()
        with urllib.request.urlopen(base + "/app.js") as response:
            assert response.status == 200
            assert "setInterval(poll,5000)" in response.read().decode()
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base + "/secrets")
        assert exc.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_external_bind_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["fresh_research_dashboard", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        dash.main()

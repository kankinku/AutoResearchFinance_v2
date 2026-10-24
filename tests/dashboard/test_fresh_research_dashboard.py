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
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?)", (sid, 12, 2, "AWAITING_PROVIDER", "c" * 64)
        )
        for i in (1, 2):
            evidence = "a" * 64 if i == 1 else "b" * 64
            obj = {
                "metrics": {
                    "total_return": 0.1 * i,
                    "cagr": 0.01 * i,
                    "max_drawdown": 0.05 * i,
                    "trade_count": 45 if i == 2 else 10,
                    "exposure": 0.3,
                    "sharpe": 1.2,
                },
                "previous_evidence_hash": None if i == 1 else ("z" * 64 if corrupt else "a" * 64),
            }
            db.execute(
                "INSERT INTO generations VALUES (?,?,?,?)", (sid, i, json.dumps(obj), evidence)
            )
    with sqlite3.connect(data / "gateway.sqlite") as db:
        db.execute("CREATE TABLE stages (session_id TEXT, phase TEXT)")
        db.execute(
            "CREATE TABLE generation_timings (session_id TEXT,generation INTEGER,"
            "start_utc TEXT,end_utc TEXT)"
        )
        db.execute("INSERT INTO stages VALUES (?,?)", (sid, "AWAITING_PLAN"))
        db.execute(
            "INSERT INTO generation_timings VALUES (?,?,?,?)",
            (sid, 1, "2026-10-20T00:00:00+00:00", "2026-10-20T00:01:30+00:00"),
        )
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
    assert a["generations"][1]["cagr"] == 0.02
    assert 0.18 < a["qqq_dev_bh_cagr"] < 0.20
    assert a["orders_enabled"] is False
    assert a["model_autonomy_verified"] is False
    assert a["generations"][0]["eligible"] is False
    assert a["generations"][1]["eligible"] is True
    # A read-only dashboard never creates -wal or -shm as a side effect.
    assert sorted(p.name for p in (state / "research/academic-gpt-checkpoints").iterdir()) == [
        "cycles.sqlite",
        "gateway.sqlite",
    ]


def test_snapshot_preserves_undefined_risk_statistics_without_crashing(
    tmp_path: Path,
) -> None:
    state = _fixture(tmp_path)
    path = state / "research/academic-gpt-checkpoints/cycles.sqlite"
    with sqlite3.connect(path) as db:
        evidence = json.loads(
            db.execute("SELECT evidence_json FROM generations WHERE generation=1").fetchone()[0]
        )
        evidence["metrics"].update(
            {
                "trade_count": 0,
                "sharpe": None,
                "sortino": None,
                "profit_factor": None,
                "win_rate": None,
            }
        )
        db.execute(
            "UPDATE generations SET evidence_json=? WHERE generation=1",
            (json.dumps(evidence),),
        )
    view = dash.snapshot(state)
    first = view["generations"][0]
    assert view["proof_chain_ok"] is True
    assert first["trades"] == 0
    assert first["sharpe"] is None
    assert first["sortino"] is None
    assert first["profit_factor"] is None
    assert first["win_rate"] is None
    assert '"sharpe": null' in json.dumps(view)


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


def test_current_100_generation_default_is_pinned_and_keeps_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archived = _fixture(tmp_path / "original")
    active = _fixture(tmp_path / "cohort")
    sid = "1" * 32
    # A tiny synthetic G452 checkpoint and two appended generations. This test
    # validates source isolation/manifest pinning, not strategy profitability.
    with sqlite3.connect(active / "research/academic-gpt-checkpoints/cycles.sqlite") as db:
        db.execute("UPDATE sessions SET requested=552,completed=454 WHERE id=?", (sid,))
        db.execute("DELETE FROM generations")
        prev = None
        for g in range(1, 455):
            h = f"{g:064x}"
            data = {
                "metrics": {
                    "total_return": 0.04,
                    "cagr": 0.01,
                    "max_drawdown": 0.12,
                    "trade_count": 31,
                    "exposure": 0.3,
                    "sharpe": 0.1,
                },
                "previous_evidence_hash": prev,
            }
            db.execute(
                "INSERT INTO generations VALUES (?,?,?,?)",
                (sid, g, json.dumps(data), h),
            )
            prev = h
    cohort_id = "G453-G552-20261023-moon-stress"
    (active / "start-manifest.json").write_text(
        json.dumps(
            {
                "source_generation": 452,
                "target_final_generation": 552,
                "source_evidence_hash": f"{452:064x}",
            }
        )
    )
    (active / "cohorts").mkdir()
    (active / "cohorts" / (cohort_id + ".json")).write_text(
        json.dumps(
            {
                "id": cohort_id,
                "expected_start": 452,
                "target": 552,
                "evidence_head_at_start": f"{452:064x}",
            }
        )
    )
    monkeypatch.setattr(dash, "STATE", archived)
    monkeypatch.setattr(dash, "ACTIVE_STATE", active)
    # Explicitly simulate an environment before the new live GPT cohort.
    monkeypatch.setattr(dash, "LIVE_STATE", tmp_path / "not_started")
    current = dash.snapshot()
    assert (current["completed"], current["requested"]) == (454, 552)
    assert (current["additional_completed"], current["additional_target"]) == (2, 100)
    assert current["cohort_start_generation"] == 453
    assert current["source_kind"] == "ISOLATED_100_GENERATION_DEVELOPMENT"
    assert "고정 규칙 기반" in current["cohort_label"]
    assert current["proof_chain_ok"] is True
    saved = dash.snapshot(archived)
    assert (saved["completed"], saved["requested"]) == (2, 12)
    assert saved["source_kind"] == "ORIGINAL_ACADEMIC_DEVELOPMENT"
    (active / "start-manifest.json").write_text(
        json.dumps(
            {
                "source_generation": 452,
                "target_final_generation": 552,
                "source_evidence_hash": "wrong",
            }
        )
    )
    with pytest.raises(ValueError, match="active cohort manifest"):
        dash.snapshot()


def test_pinned_authenticated_mcp_checkpoint_default_and_legacy_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _fixture(tmp_path / "older")
    live = _fixture(tmp_path / "live")
    sid = "1" * 32
    (live / "session-id.txt").unlink()
    monkeypatch.setattr(dash, "LIVE_STATE", live)
    monkeypatch.setattr(dash, "LIVE_SESSION_ID", sid)
    monkeypatch.setattr(dash, "STATE", old)
    monkeypatch.setattr(dash, "ACTIVE_STATE", tmp_path / "no_legacy_clone")
    current = dash.snapshot()
    assert current["source_kind"] == "GPT_AUTHORED_MCP_CHECKPOINT_DEVELOPMENT"
    assert current["completed"] == 2
    assert current["requested"] == 12
    assert current["cohort_start_generation"] == 1
    assert current["additional_completed"] == 2
    assert current["proof_chain_ok"] is True
    assert current["session"] == sid[:8]
    archived = dash.snapshot(old)
    assert archived["source_kind"] == "ORIGINAL_ACADEMIC_DEVELOPMENT"
    assert archived["proof_chain_ok"] is True
    with sqlite3.connect(live / "research/academic-gpt-checkpoints/cycles.sqlite") as db:
        db.execute("DELETE FROM generations WHERE generation=2")
    corrupted = dash.snapshot()
    assert corrupted["proof_chain_ok"] is False


def test_original_html_dashboard_has_readonly_archived_link() -> None:
    from scripts.fresh_original_dashboard import page

    html = page("index.html").decode("utf-8")
    assert 'href="api/status?cohort=historical"' in html

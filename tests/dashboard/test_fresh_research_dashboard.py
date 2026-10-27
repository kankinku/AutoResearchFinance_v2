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
    monkeypatch.setattr(dash, "P5_STATE", tmp_path / "no_p5_clone")
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
    monkeypatch.setattr(dash, "P5_STATE", tmp_path / "no_p5_clone")
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
    assert 'href="api/status?cohort=p5"' in html
    assert "현재 ChatGPT Quant MCP 실시간 연구 원장" in html


def test_live_quant_is_default_even_when_stale_p5_clone_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    live = _fixture(tmp_path / "live")
    p5_fixture = _fixture(tmp_path / "other_p5")
    p5 = tmp_path / "p5-clone"
    (p5 / "academic-gpt-checkpoints").mkdir(parents=True)
    for name in ("cycles.sqlite", "gateway.sqlite"):
        shutil.copy2(
            p5_fixture / "research/academic-gpt-checkpoints" / name,
            p5 / "academic-gpt-checkpoints" / name,
        )
    with sqlite3.connect(p5 / "academic-gpt-checkpoints/cycles.sqlite") as db:
        db.execute("UPDATE sessions SET requested=100")
    monkeypatch.setattr(dash, "LIVE_STATE", live)
    monkeypatch.setattr(dash, "LIVE_SESSION_ID", "1" * 32)
    monkeypatch.setattr(dash, "P5_STATE", p5)
    monkeypatch.setattr(dash, "P5_SESSION_ID", "1" * 32)
    current = dash.snapshot()
    assert (current["completed"], current["requested"]) == (2, 12)
    assert current["cohort_label"].startswith("현재 GPT 작성 MCP")
    assert current["source_kind"] == "GPT_AUTHORED_MCP_CHECKPOINT_DEVELOPMENT"
    archived = dash.snapshot(p5)
    assert (archived["completed"], archived["requested"]) == (2, 100)
    assert "P5" in archived["cohort_label"]
    assert archived["proof_chain_ok"] is True


def test_live_dashboard_reflects_new_generation_on_next_poll_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual HTTP handler re-reads SQLite, not a pinned snapshot."""
    state = _fixture(tmp_path)
    monkeypatch.setattr(dash, "LIVE_STATE", state)
    monkeypatch.setattr(dash, "LIVE_SESSION_ID", "1" * 32)
    monkeypatch.setattr(dash, "P5_STATE", tmp_path / "unused_p5")
    server = ThreadingHTTPServer(("127.0.0.1", 0), dash.DashboardHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}/api/status"
    try:
        with urllib.request.urlopen(url) as r:
            before = json.load(r)
        assert before["completed"] == 2
        assert before["head_evidence_prefix"] == "b" * 12
        dbpath = state / "research/academic-gpt-checkpoints/cycles.sqlite"
        with sqlite3.connect(dbpath) as db:
            db.execute("UPDATE sessions SET completed=3")
            third = {
                "metrics": {
                    "total_return": 0.25,
                    "cagr": 0.03,
                    "max_drawdown": 0.08,
                    "trade_count": 51,
                    "exposure": 0.4,
                    "sharpe": 0.7,
                },
                "previous_evidence_hash": "b" * 64,
            }
            db.execute(
                "INSERT INTO generations VALUES (?,?,?,?)",
                ("1" * 32, 3, json.dumps(third), "c" * 64),
            )
        with urllib.request.urlopen(url) as r:
            after = json.load(r)
        assert after["completed"] == 3
        assert after["last"]["generation"] == 3
        assert after["head_evidence_prefix"] == "c" * 12
        assert after["proof_chain_ok"] is True
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def _add_independent_live_session(state: Path, sid: str, *, completed: int = 1) -> None:
    """Register a second MCP session on the same unmodified academic DB."""
    base = state / "research/academic-gpt-checkpoints"
    with sqlite3.connect(base / "cycles.sqlite") as db:
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (
            sid, 50, completed, "AWAITING_PROVIDER", "c" * 64,
        ))
        prev = None
        for generation in range(1, completed + 1):
            digest = f"{generation + 100:064x}"
            evidence = {
                "metrics": {
                    "total_return": 0.25 + generation * 0.01,
                    "cagr": 0.04,
                    "max_drawdown": 0.11,
                    "trade_count": 40,
                    "exposure": 0.5,
                    "sharpe": 0.8,
                },
                "previous_evidence_hash": prev,
            }
            db.execute("INSERT INTO generations VALUES (?,?,?,?)", (
                sid, generation, json.dumps(evidence), digest,
            ))
            prev = digest
    with sqlite3.connect(base / "gateway.sqlite") as db:
        db.execute("INSERT INTO stages VALUES (?,?)", (sid, "AWAITING_PLAN"))


def test_default_selects_newest_registered_live_session_and_archived_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = _fixture(tmp_path)
    old = "1" * 32
    new = "2" * 32
    monkeypatch.setattr(dash, "LIVE_STATE", live)
    monkeypatch.setattr(dash, "LIVE_SESSION_ID", old)
    monkeypatch.setattr(dash, "P5_STATE", tmp_path / "unused")
    before = dash.snapshot()
    assert before["session_id"] == old
    assert before["completed"] == 2
    _add_independent_live_session(live, new, completed=3)
    latest = dash.snapshot()
    archive = dash.snapshot(live, session_id=old)
    assert latest["session_id"] == new
    assert latest["completed"] == 3
    assert latest["requested"] == 50
    assert latest["proof_chain_ok"] is True
    assert archive["session_id"] == old
    assert archive["completed"] == 2
    assert latest["archived_best"]["session_id"] == old
    assert latest["archived_best"]["best_eligible"]["generation"] == 2
    assert latest["cohort_label"] != archive["cohort_label"]


def test_latest_session_is_requeried_without_server_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import fresh_original_dashboard as original

    live = _fixture(tmp_path)
    monkeypatch.setattr(dash, "LIVE_STATE", live)
    monkeypatch.setattr(dash, "LIVE_SESSION_ID", "1" * 32)
    monkeypatch.setattr(dash, "P5_STATE", tmp_path / "unused")
    monkeypatch.setattr(original, "snapshot", dash.snapshot)
    monkeypatch.setattr(original, "LIVE_STATE", live)
    monkeypatch.setattr(original, "LIVE_SESSION_ID", "1" * 32)
    server = ThreadingHTTPServer(("127.0.0.1", 0), original.OriginalDashboardHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(url + "/api/status") as response:
            assert json.load(response)["session_id"] == "1" * 32
        _add_independent_live_session(live, "2" * 32)
        with urllib.request.urlopen(url + "/api/status") as response:
            body = json.load(response)
            assert body["session_id"] == "2" * 32
            assert body["completed"] == 1
        with urllib.request.urlopen(url + "/api/dashboard") as response:
            payload = json.load(response)
            assert len(payload["tests"]) == 1
            assert payload["strategy"]["generation"] == 1
        with urllib.request.urlopen(url + "/api/status?cohort=prior_mcp") as response:
            assert json.load(response)["session_id"] == "1" * 32
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_invalid_live_session_id_fails_closed_without_untrusted_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = _fixture(tmp_path)
    with sqlite3.connect(live / "research/academic-gpt-checkpoints/cycles.sqlite") as db:
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (
            "invalid-session", 50, 0, "AWAITING_PROVIDER", "c" * 64,
        ))
    monkeypatch.setattr(dash, "LIVE_STATE", live)
    monkeypatch.setattr(dash, "P5_STATE", tmp_path / "unused")
    with pytest.raises(ValueError, match="invalid session id"):
        dash.snapshot()


def test_backtest_run_ids_are_namespaced_to_the_research_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.fresh_original_dashboard import backtest, compat

    live = _fixture(tmp_path)
    monkeypatch.setattr(dash, "LIVE_STATE", live)
    monkeypatch.setattr(dash, "LIVE_SESSION_ID", "1" * 32)
    old = dash.snapshot()
    _add_independent_live_session(live, "2" * 32)
    new = dash.snapshot()
    old_runs = compat(old)["tests"]
    new_runs = compat(new)["tests"]
    assert old_runs[0]["run_id"] != new_runs[0]["run_id"]
    assert "11111111" in old_runs[0]["run_id"]
    assert "22222222" in new_runs[0]["run_id"]
    assert backtest(new, compat(new))["summary"]["best_run_id"] == new_runs[0]["run_id"]
    assert backtest(old, compat(old))["summary"]["best_run_id"] == old_runs[0]["run_id"]


def test_current_cohort_rejects_uncommitted_newest_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = _fixture(tmp_path)
    with sqlite3.connect(live / "research/academic-gpt-checkpoints/cycles.sqlite") as db:
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (
            "2" * 32, 50, 0, "AWAITING_PROVIDER", "c" * 64,
        ))
    monkeypatch.setattr(dash, "LIVE_STATE", live)
    monkeypatch.setattr(dash, "P5_STATE", tmp_path / "unused")
    with pytest.raises(ValueError, match="session not found"):
        dash.snapshot()

"""Bounded-batch monitor is distinct from GPT-authored cohort and read-only."""

from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts import fresh_original_dashboard as dashboard
from scripts.quant_batch_live_bridge import batch_snapshot


def _fixture_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE batches (id TEXT PRIMARY KEY, status TEXT NOT NULL, request_json TEXT NOT NULL,
       requested INTEGER NOT NULL, completed INTEGER NOT NULL, created REAL NOT NULL,
       started REAL, finished REAL, pid INTEGER, heartbeat REAL, cancel INTEGER,
       research_run_id TEXT, error_code TEXT);
    CREATE TABLE generation_history (batch_id TEXT NOT NULL, generation INTEGER NOT NULL,
       seconds REAL NOT NULL, method TEXT NOT NULL, count INTEGER NOT NULL,
       parent_id TEXT NOT NULL, successor_id TEXT NOT NULL, result_status TEXT NOT NULL,
       result_counts TEXT NOT NULL, candidate_count INTEGER NOT NULL,
       PRIMARY KEY(batch_id, generation));
    """)
    db.execute(
        "INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("oldbatch", "COMPLETED", "{}", 100, 100, 1000, 1000, 1002, None, 1002, 0, "oldrun", None),
    )
    db.execute(
        "INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("newbatch", "RUNNING", "{}", 10, 2, 2000, 2000, None, 123, 2004, 0, "newrun", None),
    )
    for g, count, skipped in [(1, 8, 0), (2, 5, 3)]:
        db.execute(
            "INSERT INTO generation_history VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "newbatch",
                g,
                1.5,
                "random",
                8,
                "mean_reversion",
                "mean_reversion",
                "COMPLETED",
                json.dumps({"REJECT": count, "DUPLICATE_SKIPPED": skipped}),
                count,
            ),
        )
    db.commit()
    return db


def test_batch_snapshot_polls_committed_counts_and_tracks_completion(tmp_path: Path) -> None:
    path = tmp_path / "batch.sqlite"
    db = _fixture_db(path)
    try:
        current = batch_snapshot(path)
        assert current["batch"]["batch_id"] == "newbatch"
        assert (current["batch"]["completed"], current["batch"]["requested"]) == (2, 10)
        assert current["batch"]["candidates_evaluated"] == 13
        assert current["batch"]["duplicate_skipped"] == 3
        assert current["batch"]["rejected"] == 13
        assert current["batch"]["promoted"] == 0
        assert [g["generation"] for g in current["batch"]["generations"]] == [1, 2]
        assert current["batch"]["checkpoints_consistent"] is True
        assert current["research_type"] == "FIXED_PARAMETER_BACKTEST_NOT_GPT_EVOLUTION"
        assert current["orders_enabled"] is False
        db.execute(
            "UPDATE batches SET completed=3, status='COMPLETED', finished=2008 WHERE id='newbatch'"
        )
        db.execute(
            "INSERT INTO generation_history VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "newbatch",
                3,
                1.2,
                "random",
                8,
                "mean_reversion",
                "mean_reversion",
                "COMPLETED",
                json.dumps({"REJECT": 4, "DUPLICATE_SKIPPED": 4}),
                4,
            ),
        )
        db.commit()
        updated = batch_snapshot(path)
        assert updated["batch"]["completed"] == 3
        assert updated["batch"]["candidates_evaluated"] == 17
        assert updated["batch"]["checkpoints_consistent"] is True
    finally:
        db.close()


def test_batch_http_endpoint_is_readonly_and_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "batch.sqlite"
    db = _fixture_db(path)
    monkeypatch.setattr(dashboard, "BATCH_DB_PATH", path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.OriginalDashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(url + "/api/research-batches/latest") as res:
            assert res.status == 200
            assert res.headers["Cache-Control"] == "no-store, max-age=0"
            assert json.load(res)["batch"]["batch_id"] == "newbatch"
        html = dashboard.page("index.html").decode()
        assert 'id="batch-progress"' in html
        assert 'src="static/fresh-batch.js"' in html
        assert 'id="perf-return-chart"' in html
        with urllib.request.urlopen(url + "/static/fresh-batch.js") as res:
            js = res.read().decode()
        assert 'fetch("api/research-batches/latest"' in js
        assert "setInterval(refreshBatch,5000)" in js
        req = urllib.request.Request(url + "/api/research-batches/latest", method="POST", data=b"")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 405
    finally:
        db.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

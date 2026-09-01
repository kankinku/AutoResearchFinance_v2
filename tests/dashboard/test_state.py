from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard.state import DashboardStateReader, SnapshotStore


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_reader_builds_paper_only_snapshot_from_state_files(tmp_path: Path) -> None:
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    _write(
        tmp_path / "mode.json",
        {"schema_version": 1, "selected_mode": "live", "orders_enabled": True},
    )
    _write(
        tmp_path / "champion.json",
        {
            "schema_version": 1,
            "status": "CHAMPION",
            "champion_hash": "champion-1",
            "family": "macro",
            "score": 0.84,
            "generation": 4,
            "feature_ids": ["vix_percentile", "us_10y_change"],
        },
    )
    _write(
        tmp_path / "knowledge.json",
        {
            "schema_version": 1,
            "generation": 4,
            "known_good": [
                {
                    "candidate_hash": "candidate-1",
                    "family": "macro",
                    "generation": 4,
                    "score": 0.84,
                    "status": "SURVIVOR",
                    "nasdaq_excess_return": 0.12,
                    "max_daily_loss_pct": 2.1,
                    "risk_compliant": True,
                }
            ],
        },
    )
    (tmp_path / "test-records.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"run_id": "run-1", "strategy_hash": "candidate-1", "generation": 4, "timestamp": "2026-09-01T10:00:00+00:00", "total_return": 0.2, "nasdaq_excess_return": 0.12, "max_drawdown": 0.05, "risk_compliant": True, "status": "SURVIVOR"}),
                json.dumps({"run_id": "run-0", "strategy_hash": "candidate-0", "generation": 3, "timestamp": "2026-08-31T10:00:00+00:00", "total_return": 0.1, "nasdaq_excess_return": -0.02, "max_drawdown": 0.08, "risk_compliant": True, "status": "REJECT"}),
            ]
        ),
        encoding="utf-8",
    )
    heartbeat_dir = tmp_path / "worker-heartbeats"
    heartbeat_dir.mkdir()
    _write(
        heartbeat_dir / "worker-1.json",
        {"worker_id": "worker-1", "job_id": "job-1", "role": "backtest", "status": "RUNNING", "last_heartbeat": (now - timedelta(seconds=20)).isoformat(), "attempt": 1},
    )

    snapshot = DashboardStateReader(tmp_path, clock=lambda: now).read()

    assert snapshot.mode.effective_mode == "paper"
    assert snapshot.mode.live_enabled is False
    assert snapshot.account.status == "UNKNOWN"
    assert snapshot.strategy.champion_hash == "champion-1"
    assert snapshot.strategy.feature_ids == ["vix_percentile", "us_10y_change"]
    assert snapshot.tests[0].run_id == "run-1"
    assert snapshot.trend[0].generation == 3
    assert snapshot.workers[0].online_state == "ONLINE"
    assert "LIVE_MODE_REJECTED" in snapshot.warning_codes


def test_reader_masks_account_and_classifies_stale_and_offline_workers(tmp_path: Path) -> None:
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    _write(tmp_path / "account.json", {"status": "ONLINE", "account_number": "12345678-01", "equity": 10000, "cash": 7000, "buying_power": 7000, "holdings": []})
    heartbeat_dir = tmp_path / "worker-heartbeats"
    heartbeat_dir.mkdir()
    _write(heartbeat_dir / "stale.json", {"worker_id": "stale", "job_id": "job-2", "role": "search", "status": "RUNNING", "last_heartbeat": (now - timedelta(seconds=120)).isoformat()})
    _write(heartbeat_dir / "offline.json", {"worker_id": "offline", "job_id": "job-3", "role": "search", "status": "RUNNING", "last_heartbeat": (now - timedelta(seconds=600)).isoformat()})

    snapshot = DashboardStateReader(tmp_path, clock=lambda: now).read()

    assert snapshot.account.account_number == "******78-01"
    assert {worker.online_state for worker in snapshot.workers} == {"STALE", "OFFLINE"}


def test_snapshot_store_writes_and_reads_validated_json(tmp_path: Path) -> None:
    snapshot = DashboardStateReader(tmp_path).read()
    store = SnapshotStore(tmp_path / "dashboard.json")

    store.write(snapshot)
    restored = store.read()

    assert restored is not None
    assert restored.schema_version == 1
    assert restored.mode.effective_mode == "paper"

"""Phase 1 audit must not alter an active checkpoint or misstate discovery."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from evaluation.academic_campaign_audit import audit_campaign, snapshot_ledger


def _fixture(checkpoint: Path, *, corrupt: bool = False) -> None:
    checkpoint.mkdir()
    with sqlite3.connect(checkpoint / "cycles.sqlite") as db:
        db.executescript("""
        CREATE TABLE sessions (
            id TEXT, requested INTEGER, completed INTEGER,
            status TEXT, dataset_hash TEXT
        );
        CREATE TABLE generations (
            session_id TEXT, generation INTEGER,
            evidence_json TEXT, evidence_hash TEXT
        );
        """)
        for name, completed in (("old", 2), ("new", 3)):
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?)",
                (name, 3, completed, "AWAITING_PROVIDER", "data-1"),
            )
            for generation in range(1, completed + 1):
                data = {
                    "generation": generation,
                    "dataset_hash": "data-1",
                    "strategy_hash": f"strategy-{name}-{generation}",
                    "metrics": {
                        "total_return": 0.5,
                        "max_drawdown": 0.1,
                        "exposure": 0.3,
                        "trade_count": 32,
                    },
                    "independent_oos_approved": False,
                    "experiments": [{"hypothesis_id": "h", "observed_ids": ["trade-1"]}],
                }
                db.execute(
                    "INSERT INTO generations VALUES (?,?,?,?)",
                    (name, generation, json.dumps(data), "a" * 64),
                )
    with sqlite3.connect(checkpoint / "gateway.sqlite") as db:
        db.executescript("""
        CREATE TABLE stages (session_id TEXT,phase TEXT);
        CREATE TABLE experiment_reports (
            session_id TEXT, generation INTEGER,
            report_json TEXT, report_hash TEXT
        );
        CREATE TABLE parent_selections (
            session_id TEXT, next_generation INTEGER,
            selection_json TEXT, selection_hash TEXT
        );
        """)
        db.executemany(
            "INSERT INTO stages VALUES (?,?)", [("old", "COMPLETED"), ("new", "AWAITING_PLAN")]
        )
        for name, completed in (("old", 2), ("new", 3)):
            for generation in range(1, completed + 1):
                child = "same-child" if generation < 3 else "new-child"
                experiment = {
                    "parent_final_equity": 15000.0,
                    "child_final_equity": [15100.0, 14800.0, 15100.0][generation - 1],
                    "child_strategy_hash": child,
                    "same_fill_trace": generation == 2,
                    "child_fill_count": 60,
                    "status": "DIRECTION_MATCHED_DEVELOPMENT_ONLY",
                    "metric": "trade_count",
                    "execution_delta": {"parent_costs": 150.0, "child_costs": 180.0},
                }
                payload = {"report": {"experiments": [experiment], "out_of_sample_approved": False}}
                if corrupt and name == "new" and generation == 3:
                    continue
                db.execute(
                    "INSERT INTO experiment_reports VALUES (?,?,?,?)",
                    (name, generation, json.dumps(payload), "report-hash"),
                )
        db.execute(
            "INSERT INTO parent_selections VALUES (?,?,?,?)",
            (
                "new",
                4,
                json.dumps(
                    {
                        "source_generation": 2,
                        "parent_quality": {
                            "total_return": 0.49,
                            "max_drawdown": 0.08,
                            "closed_trades": 32,
                            "market_exposure": 0.30,
                            "qqq_buy_and_hold_return": 1.8,
                        },
                    }
                ),
                "sel-hash",
            ),
        )


def test_snapshot_and_economic_diversity_audit_are_read_only(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _fixture(source)
    out = tmp_path / "frozen"
    manifest = snapshot_ledger(source, out)
    report = audit_campaign(out, origin_session="old", active_session="new")
    assert manifest["files"]["cycles.sqlite"]["sha256"]
    assert report["generation_count"] == 5
    assert report["active_s7"]["better"] == 2
    assert report["active_s7"]["worse"] == 1
    assert report["active_s7"]["matched_but_worse"] == 1
    assert report["active_s7"]["unchanged_execution"] == 1
    assert report["active_s7"]["duplicate_child_hashes"] == 1
    assert report["active_s7"]["cost_delta_total"] == pytest.approx(90)
    assert report["risk_flags"]["independent_oos_unverified"] is True
    assert report["risk_flags"]["same_development_dataset"] is True
    assert report["latest_selected_parent"]["mdd"] == pytest.approx(0.08)
    with sqlite3.connect(source / "cycles.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM generations").fetchone()[0] == 5


def test_missing_s7_generation_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _fixture(source, corrupt=True)
    out = tmp_path / "frozen"
    snapshot_ledger(source, out)
    with pytest.raises(ValueError, match="generation mismatch"):
        audit_campaign(out, origin_session="old", active_session="new")


def test_snapshot_does_not_overwrite_existing_freeze(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _fixture(source)
    out = tmp_path / "frozen"
    snapshot_ledger(source, out)
    with pytest.raises(FileExistsError):
        snapshot_ledger(source, out)


def test_snapshot_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _fixture(source)
    out = tmp_path / "frozen"
    snapshot_ledger(source, out)
    with (out / "cycles.sqlite").open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="checksum mismatch"):
        audit_campaign(out, origin_session="old", active_session="new")

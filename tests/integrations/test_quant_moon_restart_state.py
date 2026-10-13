"""Restart acceptance must preserve state and must fail closed for mutation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from memory.evidence_store import EvidenceStore
from scripts.verify_quant_moon_restart import RestartVerificationError, capture, verify


def _state(tmp_path: Path) -> Path:
    root = tmp_path / "research"
    oauth = root / "oauth"
    oauth.mkdir(parents=True)
    (tmp_path / "oauth").mkdir()
    (tmp_path / "oauth" / "approval-key").write_text("random-example-" + "a" * 60)
    (tmp_path / "oauth" / "public-base-url").write_text("https://moon.example.ts.net/quant\n")
    with sqlite3.connect(oauth / "quant-oauth.sqlite") as conn:
        conn.execute("CREATE TABLE clients (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        conn.execute("INSERT INTO clients VALUES ('client-one', '{}')")
        conn.execute(
            "CREATE TABLE grants (digest TEXT PRIMARY KEY, kind TEXT, client_id TEXT, "
            "payload TEXT, expires REAL)"
        )
        conn.execute(
            "INSERT INTO grants VALUES ('opaque-hash', 'access', 'client-one', '{}', 9999999999)"
        )
    system = root / "system"
    system.mkdir()
    with sqlite3.connect(system / "gpt-research-batches.sqlite") as conn:
        conn.execute(
            "CREATE TABLE batches (id TEXT PRIMARY KEY, status TEXT, completed INTEGER, "
            "requested INTEGER, research_run_id TEXT, error_code TEXT)"
        )
        conn.execute("INSERT INTO batches VALUES ('b1', 'COMPLETED', 2, 2, 'r1', NULL)")
        conn.execute(
            "CREATE TABLE generation_history (batch_id TEXT, generation INTEGER, "
            "result_status TEXT)"
        )
        conn.execute("INSERT INTO generation_history VALUES ('b1', 1, 'REJECT')")
        conn.execute(
            "CREATE TABLE generation_checkpoints (batch_id TEXT, generation INTEGER, "
            "payload_json TEXT)"
        )
        conn.execute("INSERT INTO generation_checkpoints VALUES ('b1', 1, '{}')")
    with sqlite3.connect(system / "gpt-guided-sessions.sqlite") as conn:
        conn.execute(
            "CREATE TABLE sessions (id TEXT, status TEXT, completed INTEGER, requested INTEGER, "
            "token TEXT, previous_run_id TEXT)"
        )
        conn.execute(
            "INSERT INTO sessions VALUES ('g1', 'AWAITING_GPT', 1, 2, 'sensitive-token', 'r1')"
        )
        conn.execute("CREATE TABLE steps (session_id TEXT, generation INTEGER, run_id TEXT)")
    store = EvidenceStore(root)
    store.append(
        "run",
        "run:r1",
        {
            "research_run_id": "r1",
            "requested_generations": 2,
            "seed": 1,
        },
    )
    return tmp_path


def test_restart_roundtrip_preserves_read_only_operational_state(tmp_path: Path) -> None:
    root = _state(tmp_path)
    baseline = capture(root)
    report = verify(root, baseline)
    assert report["status"] == "PASS"
    assert report["orders_enabled"] is False
    assert report["oauth_clients"] == 1
    assert report["evidence_events"] == 1
    assert "sensitive-token" not in str(baseline)
    assert "client-one" not in str(baseline)
    assert "random-example-" not in str(baseline)


def test_restart_detects_oauth_key_change_and_persistent_session_change(tmp_path: Path) -> None:
    root = _state(tmp_path)
    baseline = capture(root)
    (root / "oauth" / "approval-key").write_text("changed-" + "b" * 64)
    with pytest.raises(RestartVerificationError, match="approval"):
        verify(root, baseline)
    (root / "oauth" / "approval-key").write_text("random-example-" + "a" * 60)
    db = root / "research" / "system" / "gpt-guided-sessions.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET token='changed-token'")
    with pytest.raises(RestartVerificationError, match="guided"):
        verify(root, baseline)


def test_restart_rejects_running_batch_and_corrupted_evidence(tmp_path: Path) -> None:
    root = _state(tmp_path)
    baseline = capture(root)
    db = root / "research" / "system" / "gpt-research-batches.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE batches SET status='RUNNING'")
    with pytest.raises(RestartVerificationError, match="active"):
        capture(root)
    with pytest.raises(RestartVerificationError, match="active"):
        verify(root, baseline)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE batches SET status='COMPLETED'")
    epath = root / "research" / "system" / "research-evidence" / "evidence.sqlite"
    with sqlite3.connect(epath) as conn:
        conn.execute("DROP TRIGGER prevent_update")
        conn.execute("UPDATE events SET checksum='tampered'")
    with pytest.raises(RestartVerificationError, match="Evidence|evidence"):
        verify(root, baseline)


def test_restart_refuses_missing_oauth_identity_without_recreating_it(tmp_path: Path) -> None:
    root = _state(tmp_path)
    baseline = capture(root)
    file = root / "research" / "oauth" / "quant-oauth.sqlite"
    file.unlink()
    with pytest.raises(RestartVerificationError, match="OAuth|oauth"):
        verify(root, baseline)
    assert not file.exists()


def test_windows_restart_wrapper_is_opt_in_and_secret_safe() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "verify_quant_windows_container_restart.ps1"
    ).read_text(encoding="utf-8")
    assert "[switch] $RestartContainer" in script
    assert "if (-not $RestartContainer)" in script
    assert script.index("if (-not $RestartContainer)") < script.index("docker restart $Container")
    assert "scripts.verify_quant_moon_restart" in script
    assert 'Read-ContainerProbe -Path $baseline -Stage "before"' in script
    assert 'Read-ContainerProbe -Path $baseline -Stage "after"' in script
    assert "HOST_REBOOT_ACCEPTANCE=NOT_TESTED" in script
    assert "WINDOWS_DOCKER_RESTART=BLOCKED" in script
    assert "WINDOWS_DOCKER_RESTART=PASS" in script
    assert "docker rm " not in script
    assert "Get-Content " not in script


def test_restart_cli_creates_private_baseline_and_no_key_output(tmp_path: Path) -> None:
    import json
    import subprocess
    import sys

    root = _state(tmp_path)
    baseline = tmp_path / "private" / "restart.json"
    command = [
        sys.executable,
        "-m",
        "scripts.verify_quant_moon_restart",
        "before",
        "--moon-state",
        str(root),
        "--baseline",
        str(baseline),
    ]
    output = subprocess.run(command, text=True, capture_output=True, check=True)
    assert json.loads(output.stdout)["status"] == "BASELINE_CAPTURED"
    assert "random-example-" not in output.stdout
    assert "sensitive-token" not in output.stdout
    assert baseline.stat().st_mode & 0o777 == 0o600
    assert "client-one" not in baseline.read_text(encoding="utf-8")
    second = command.copy()
    second[3] = "after"
    verified = subprocess.run(second, text=True, capture_output=True, check=True)
    assert json.loads(verified.stdout)["status"] == "PASS"
    assert json.loads(verified.stdout)["orders_enabled"] is False

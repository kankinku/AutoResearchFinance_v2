from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.supervisor.service import SupervisorService


def make_command(command: str, **overrides: object) -> dict[str, object]:
    payload = {
        "command": command,
        "project_id": "finance",
        "source": "openclaw",
        "requested_by": "router",
        "requested_at": "2026-03-25T00:00:00+00:00",
        "payload": {},
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStateStore:
    repository = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    yield repository
    repository.close()


def test_openclaw_control_defaults_project_id_and_returns_normalized_status(
    store: SQLiteStateStore,
) -> None:
    from finance_autoresearch.integrations.openclaw_control import (
        OpenClawControlAdapter,
    )

    supervisor = SupervisorService(
        state_store=store,
        seed_validator=lambda _project_id: (True, "seed baseline validated"),
        run_id_factory=lambda: "run-001",
    )
    adapter = OpenClawControlAdapter(supervisor=supervisor, default_project_id="finance")

    exit_code, stdout, stderr = adapter.run(
        json.dumps(make_command("status", project_id=None))
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout) == {
        "accepted": True,
        "project_state": "idle",
        "pipeline_state": "idle",
        "autoresearch_state": "idle",
        "pending_command": None,
        "message": "status retrieved",
        "run_id": None,
    }


def test_openclaw_control_rejects_invalid_stdin_schema(
    store: SQLiteStateStore,
) -> None:
    from finance_autoresearch.integrations.openclaw_control import (
        OpenClawControlAdapter,
    )

    supervisor = SupervisorService(
        state_store=store,
        seed_validator=lambda _project_id: (True, "seed baseline validated"),
        run_id_factory=lambda: "run-001",
    )
    adapter = OpenClawControlAdapter(supervisor=supervisor, default_project_id="finance")

    exit_code, stdout, stderr = adapter.run('{"command":"status","payload":[]}')

    assert exit_code != 0
    assert stdout == ""
    assert "invalid command" in stderr


def test_python_module_openclaw_control_subprocess_exit_code_and_stdout(
    tmp_path: Path,
) -> None:
    state_db_path = tmp_path / "state.db"
    SQLiteStateStore(db_path=state_db_path, project_id="finance").close()

    env = os.environ.copy()
    env["FINANCE_AUTORESEARCH_STATE_DB_PATH"] = str(state_db_path)
    env["FINANCE_AUTORESEARCH_PROJECT_ID"] = "finance"

    process = subprocess.run(
        [sys.executable, "-m", "finance_autoresearch", "openclaw-control"],
        input=json.dumps(make_command("status", project_id=None)),
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=str(Path.cwd()),
    )

    assert process.returncode == 0
    assert json.loads(process.stdout) == {
        "accepted": True,
        "project_state": "idle",
        "pipeline_state": "idle",
        "autoresearch_state": "idle",
        "pending_command": None,
        "message": "status retrieved",
        "run_id": None,
    }
    assert process.stderr == ""

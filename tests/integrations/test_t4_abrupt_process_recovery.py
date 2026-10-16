"""T4 actual subprocess-death integration, independent of the live MCP worker.

A disposable research worker commits a generation, exits *without* gateway S7
acknowledgement, and a fresh server process reconciles the immutable evidence.
This intentionally never kills or restarts the production HTTP/OAuth process.
"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
from typing import Any

from application.academic_checkpoint_service import (
    AcademicMCPCheckpointService,
    _SubmittedProvider,
)
from integrations.codex_mcp_core import create_mcp_server
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _crash_after_cycle_commit(
    project: str,
    state: str,
    staged: dict[str, Any],
    marker: str,
) -> None:
    svc = AcademicMCPCheckpointService(
        project_root=Path(project), state_dir=Path(state),
    )
    sid = staged["session_id"]
    with svc._connect() as db:
        row = db.execute("SELECT * FROM stages WHERE session_id=?", (sid,)).fetchone()
        assert row is not None and row["phase"] == "AWAITING_DIAGNOSIS"
        plan = json.loads(row["plan_json"])
        catalog = svc._catalog(row["catalog_version"])
        market = svc._data(row["data_path"])
        changed = db.execute(
            "UPDATE stages SET phase='RUNNING' "
            "WHERE session_id=? AND phase='AWAITING_DIAGNOSIS'",
            (sid,),
        )
        assert changed.rowcount == 1
    diagnosis = ScriptedResearcher().propose(staged["model_context"])
    complete = svc.cycle.advance(
        sid, catalog, market, _SubmittedProvider(plan, diagnosis),
    )
    assert complete["completed_generations"] == 1
    Path(marker).write_text(
        complete["history"][0]["evidence_hash"], encoding="ascii",
    )
    # Not normal process shutdown: skip atexit/finally and gateway
    # S7 acknowledgement to reproduce a lost reply + stale RUNNING phase.
    os._exit(91)


def test_abrupt_real_worker_exit_preserves_generation_and_rebuilds_s7(
    tmp_path: Path,
) -> None:
    server, started = _setup(tmp_path)
    sid = started["session_id"]
    model = ScriptedResearcher()
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": sid,
        "checkpoint_token": started["checkpoint_token"],
        "plan": model.propose(started["model_context"]),
    })
    marker = tmp_path / "committed_evidence_hash"
    worker = multiprocessing.get_context("spawn").Process(
        target=_crash_after_cycle_commit,
        args=(
            str(tmp_path / "project"),
            str(tmp_path / "state"),
            staged,
            str(marker),
        ),
    )
    worker.start()
    worker.join(timeout=90)
    if worker.is_alive():
        worker.kill()
        worker.join(timeout=5)
    assert worker.exitcode == 91
    assert marker.is_file()
    committed_hash = marker.read_text(encoding="ascii")
    assert len(committed_hash) == 64

    # New server instance must not replay already-committed trades.
    replacement = create_mcp_server(
        project_root=tmp_path / "project",
        state_dir=tmp_path / "state",
    )
    recovered = replacement._dispatch(
        "reconcile_algorithm_research", {"session_id": sid},
    )
    assert recovered["checkpoint_phase"] == "AWAITING_PLAN"
    assert recovered["completed_generations"] == 1
    assert recovered["history"][0]["evidence_hash"] == committed_hash
    s7 = recovered["latest_controlled_experiments"]
    assert s7["original_generation_evidence_hash"] == committed_hash
    assert len(s7["report"]["experiments"]) == 1
    assert recovered == replacement._dispatch(
        "reconcile_algorithm_research", {"session_id": sid},
    )

    next_staged = replacement._dispatch("submit_algorithm_plan", {
        "session_id": sid,
        "checkpoint_token": recovered["checkpoint_token"],
        "plan": model.propose(recovered["model_context"]),
    })
    final = replacement._dispatch("submit_algorithm_diagnosis", {
        "session_id": sid,
        "checkpoint_token": next_staged["checkpoint_token"],
        "diagnosis": model.propose(next_staged["model_context"]),
    })
    assert final["status"] == final["checkpoint_phase"] == "COMPLETED"
    assert final["completed_generations"] == 2
    assert final["history"][0]["evidence_hash"] == committed_hash
    assert final["final_report"]["tested_hypotheses"] == 2
    assert final["final_report"]["all_proposed_hypotheses_measured"] is True
    assert final["final_report"]["model_autonomy_verified"] is False
    assert final["orders_enabled"] is False

    for gen in (1, 2):
        evidence = replacement._dispatch("evaluate_algorithm_experiments", {
            "session_id": sid, "generation": gen,
        })
        assert evidence["original_generation_evidence_hash"] == (
            final["history"][gen - 1]["evidence_hash"]
        )
        assert len(evidence["report"]["experiments"]) == 1

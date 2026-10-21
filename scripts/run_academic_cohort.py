"""One-command, auditable 100-generation academic cohort extension and resume.

No broker, live trading, independent OOS, or per-generation external GPT call.
This is the existing deterministic checkpoint-backed research controller.
For exact resume, rerun with the SAME --cohort-id and --expected-start values.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from scripts.fresh_development_cohort_controller_20261021 import main as run_generations

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state/moon-http/fresh-20261021"
JOBS = STATE / "cohorts"
BACKUPS = ROOT / "state/moon-http/backups"


def atomic_json(path: Path, content: dict[str, Any]) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(content, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temp, path)


def checkpoint(svc: AcademicMCPCheckpointService, sid: str) -> dict[str, Any]:
    result = svc.get({"session_id": sid})
    history = result["history"]
    completed = result["completed_generations"]
    if not history or len(history) != completed:
        raise RuntimeError("CORRUPT_EVIDENCE_HEAD")
    if not all(
        history[i]["previous_evidence_hash"] == history[i - 1]["evidence_hash"]
        for i in range(1, len(history))
    ):
        raise RuntimeError("CORRUPT_EVIDENCE_CHAIN")
    if result["orders_enabled"] or result["independent_oos_approved"]:
        raise RuntimeError("UNEXPECTED_LIVE_OR_OOS_APPROVAL")
    return cast(dict[str, Any], result)


def perform_backup(
    svc: AcademicMCPCheckpointService, folder: Path, sid: str, start: int, target: int, head: str
) -> dict[str, str]:
    folder.mkdir(parents=True, exist_ok=False)
    filehashes: dict[str, str] = {}
    for original in sorted(svc.state.glob("*.sqlite")):
        destination = folder / original.name
        with sqlite3.connect("file:" + str(original.resolve()) + "?mode=ro", uri=True) as src:
            with sqlite3.connect(destination) as copy:
                src.backup(copy)
        with sqlite3.connect(destination) as verified:
            if verified.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("BACKUP_INTEGRITY_FAILED_" + original.name)
        filehashes[original.name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    if len(filehashes) < 2:
        raise RuntimeError("BACKUP_MISSING_DB")
    atomic_json(
        folder / "manifest.json",
        {
            "session_id": sid,
            "old_completed": start,
            "new_target": target,
            "previous_head": head,
            "sqlite_sha256": filehashes,
            "created_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    return filehashes


def run(cohort_id: str, expected_start: int, additional: int) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,100}", cohort_id):
        raise ValueError("cohort_id must be a simple stable identifier")
    if not 1 <= additional <= 100 or not 1 <= expected_start <= 399:
        raise ValueError("invalid cohort size or expected_start")
    target = expected_start + additional
    if target > 400:
        raise ValueError("academic checkpoint upper bound is G400")
    JOBS.mkdir(parents=True, exist_ok=True)
    # Held for extension AND generation execution; a second invoker cannot
    # race or double-extend the same research state.
    with (JOBS / "academic-operator.lock").open("a+") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("ANOTHER_ACADEMIC_COHORT_IS_RUNNING") from exc
        session_id = (STATE / "session-id.txt").read_text(encoding="utf-8").strip()
        svc = AcademicMCPCheckpointService(project_root=ROOT, state_dir=STATE / "research")
        first = checkpoint(svc, session_id)
        record_path = JOBS / (cohort_id + ".json")
        record = json.loads(record_path.read_text()) if record_path.is_file() else None
        if record is None:
            if not (
                first["completed_generations"] == expected_start
                and first["requested_generations"] == expected_start
                and first["status"] == "COMPLETED"
                and first["checkpoint_phase"] == "COMPLETED"
                and first["final_report"]["all_proposed_hypotheses_measured"] is True
            ):
                raise RuntimeError("EXPECTED_SEALED_START_NOT_FOUND")
            head = first["history"][-1]["evidence_hash"]
            backup = BACKUPS / ("academic-" + cohort_id)
            checks = perform_backup(svc, backup, session_id, expected_start, target, head)
            record = {
                "id": cohort_id,
                "session_id": session_id,
                "expected_start": expected_start,
                "target": target,
                "requested_additional": additional,
                "evidence_head_at_start": head,
                "backup": str(backup),
                "backup_sha256": checks,
                "state": "BACKED_UP",
                "created_utc": datetime.now(timezone.utc).isoformat(),
            }
            atomic_json(record_path, record)
            print("BACKUP VERIFIED", backup, flush=True)
        if (
            record["session_id"] != session_id
            or record["expected_start"] != expected_start
            or record["target"] != target
            or record["requested_additional"] != additional
        ):
            raise RuntimeError("COHORT_ID_CONFLICT")
        existing = checkpoint(svc, session_id)
        if existing["requested_generations"] == expected_start:
            if not (
                existing["status"] == "COMPLETED"
                and existing["completed_generations"] == expected_start
                and existing["history"][-1]["evidence_hash"] == record["evidence_head_at_start"]
            ):
                raise RuntimeError("EXPECTED_OLD_SEALED_STATE_MISSING")
            extended = svc.extend_completed_session(session_id, additional_generations=additional)
            if (extended["completed_generations"], extended["requested_generations"]) != (
                expected_start,
                target,
            ):
                raise RuntimeError("EXTENSION_POSTCONDITION_FAILED")
            print("EXTENDED", expected_start, "TO", target, flush=True)
        elif existing["requested_generations"] != target:
            raise RuntimeError("TARGET_MISMATCH_NO_MUTATION")
        current = checkpoint(svc, session_id)
        if not expected_start <= current["completed_generations"] <= target:
            raise RuntimeError("GENERATIONS_OUTSIDE_COHORT")
        if (
            current["history"][expected_start - 1]["evidence_hash"]
            != record["evidence_head_at_start"]
        ):
            raise RuntimeError("ORIGINAL_COHORT_HEAD_CHANGED")
        if current["completed_generations"] == target:
            if current["status"] != "COMPLETED":
                raise RuntimeError("INCOMPLETE_FINALIZATION")
            record["state"] = "COMPLETED"
            record["completed"] = target
            record["completed_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_json(record_path, record)
            print("ALREADY COMPLETED", target, flush=True)
            return
        if current["checkpoint_phase"] != "AWAITING_PLAN":
            record["state"] = "MANUAL_CHECKPOINT_RECOVERY_REQUIRED"
            record["checkpoint_phase"] = current["checkpoint_phase"]
            atomic_json(record_path, record)
            raise RuntimeError("STAGED_PLAN_REQUIRES_AUDITED_RECOVERY")
        record["state"] = "RUNNING"
        record["completed"] = current["completed_generations"]
        record["started_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(record_path, record)
        print("RESUMING", current["completed_generations"], "OF", target, flush=True)
        try:
            run_generations(target - current["completed_generations"])
        except BaseException as exc:
            latest = checkpoint(svc, session_id)
            record["state"] = "BLOCKED"
            record["completed"] = latest["completed_generations"]
            record["checkpoint_phase"] = latest["checkpoint_phase"]
            record["failure_type"] = type(exc).__name__
            record["failure_message"] = str(exc)[:400]
            record["failed_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_json(record_path, record)
            raise
        final = checkpoint(svc, session_id)
        if (
            final["completed_generations"] != target
            or final["requested_generations"] != target
            or final["status"] != "COMPLETED"
        ):
            raise RuntimeError("UNEXPECTED_INCOMPLETE_COHORT")
        record["state"] = "COMPLETED"
        record["completed"] = target
        record["completed_utc"] = datetime.now(timezone.utc).isoformat()
        record["evidence_head_at_end"] = final["history"][-1]["evidence_hash"]
        atomic_json(record_path, record)
        print("COHORT COMPLETE", expected_start + 1, "THROUGH", target, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument("--expected-start", type=int, required=True)
    parser.add_argument("--additional", type=int, default=100)
    args = parser.parse_args()
    try:
        run(args.cohort_id, args.expected_start, args.additional)
    except BaseException:
        traceback.print_exc()
        sys.exit(1)

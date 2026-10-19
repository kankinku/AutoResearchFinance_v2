"""Operator-only safe same-ID extension of fully completed development research.

Run ONLY while the Quant MCP worker is stopped.  No orders or OOS access.
The SQLite backup directory is intentionally outside Git/state mutation paths.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--expected-completed", type=int, required=True)
    parser.add_argument("--additional", type=int, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()
    service = AcademicMCPCheckpointService(
        project_root=args.project_root,
        state_dir=args.state_dir,
    )
    before = service.get({"session_id": args.session_id})
    if (
        before["completed_generations"] != args.expected_completed
        or before["requested_generations"] != args.expected_completed
        or before["checkpoint_phase"] != "COMPLETED"
        or before["status"] != "COMPLETED"
        or before["final_report"]["all_proposed_hypotheses_measured"] is not True
    ):
        raise RuntimeError("precondition failed: completed session must be exact")
    if args.backup_dir.exists():
        raise RuntimeError("backup target already exists; refusing overwrite")
    args.backup_dir.mkdir(parents=True, mode=0o700)
    checkpoint_dir = args.state_dir / "academic-gpt-checkpoints"
    manifest: dict[str, str | int] = {
        "session_id": args.session_id,
        "old_requested": before["requested_generations"],
        "new_requested": before["requested_generations"] + args.additional,
        "completed": before["completed_generations"],
        "last_evidence_hash": before["history"][-1]["evidence_hash"],
    }
    for filename in (
        "gateway.sqlite",
        "cycles.sqlite",
        "catalog.sqlite",
        "catalog-s6-v1.sqlite",
        "catalog-s6-v2.sqlite",
    ):
        source = checkpoint_dir / filename
        if not source.is_file():
            raise RuntimeError(f"missing required database: {filename}")
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db:
            with sqlite3.connect(args.backup_dir / filename) as target_db:
                source_db.backup(target_db)
        (args.backup_dir / filename).chmod(0o600)
    manifest_file = args.backup_dir / "extension-manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_file.chmod(0o600)
    after = service.extend_completed_session(
        args.session_id,
        additional_generations=args.additional,
    )
    if (
        after["requested_generations"] != manifest["new_requested"]
        or after["completed_generations"] != manifest["completed"]
        or after["history"][-1]["evidence_hash"] != manifest["last_evidence_hash"]
    ):
        raise RuntimeError("extension postcondition failed; use operator backup to recover")
    print(
        json.dumps(
            {
                "status": after["checkpoint_phase"],
                "session_id": after["session_id"],
                "requested": after["requested_generations"],
                "completed": after["completed_generations"],
                "evidence_head": after["history"][-1]["evidence_hash"],
                "backup": str(args.backup_dir),
                "orders_enabled": after["orders_enabled"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

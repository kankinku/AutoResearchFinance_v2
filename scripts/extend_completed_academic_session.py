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


def checkpoint_backup_sources(checkpoint_dir: Path) -> tuple[Path, ...]:
    """Discover historical optional catalog stores; require the active v2 catalog.

    Validate BEFORE creating a backup target to avoid misleading partial
    backup directories. Never create missing old catalogs or substitute mocks.
    """
    required = ("gateway.sqlite", "cycles.sqlite", "catalog-s6-v2.sqlite")
    optional = ("catalog.sqlite", "catalog-s6-v1.sqlite")
    missing = [name for name in required if not (checkpoint_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"missing required checkpoint database: {', '.join(missing)}")
    return tuple(
        checkpoint_dir / name
        for name in (*required[:2], *optional, required[2])
        if (checkpoint_dir / name).is_file()
    )


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
    terminal = (
        before["status"] == "COMPLETED"
        and before["checkpoint_phase"] == "COMPLETED"
        and before["completed_generations"] == before["requested_generations"]
        and before["final_report"]["all_proposed_hypotheses_measured"] is True
    )
    idle = (
        before["status"] == "AWAITING_PROVIDER"
        and before["checkpoint_phase"] == "AWAITING_PLAN"
        and before["completed_generations"] < before["requested_generations"]
    )
    if before["completed_generations"] != args.expected_completed or not (terminal or idle):
        raise RuntimeError("precondition failed: exact idle/sealed session required")
    if args.backup_dir.exists():
        raise RuntimeError("backup target already exists; refusing overwrite")
    checkpoint_dir = args.state_dir / "academic-gpt-checkpoints"
    sources = checkpoint_backup_sources(checkpoint_dir)
    args.backup_dir.mkdir(parents=True, mode=0o700)
    manifest: dict[str, str | int] = {
        "session_id": args.session_id,
        "old_requested": before["requested_generations"],
        "new_requested": before["requested_generations"] + args.additional,
        "completed": before["completed_generations"],
        "last_evidence_hash": before["history"][-1]["evidence_hash"],
    }
    for source in sources:
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as source_db:
            with sqlite3.connect(args.backup_dir / source.name) as target_db:
                source_db.backup(target_db)
        (args.backup_dir / source.name).chmod(0o600)
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

from __future__ import annotations

import json
from pathlib import Path

from core.integrity.audit import AuditLog


def test_audit_log_records_hashes_and_actor_without_secrets(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")

    log.append("candidate_validated", actor="local", inputs={"candidate_hash": "c1"})

    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    assert record["event"] == "candidate_validated"
    assert record["actor"] == "local"
    assert record["input_hash"]
    assert "token" not in record

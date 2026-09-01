from __future__ import annotations

from pathlib import Path

import pytest

from core.integrity.audit import AuditLog
from evaluation.selector import FunnelResult
from memory.promotion import promote_candidate
from memory.state_files import StateFileStore


def test_promotion_requires_survivor_and_writes_audited_champion(tmp_path: Path) -> None:
    store = StateFileStore(tmp_path / "state")
    audit = AuditLog(tmp_path / "audit.jsonl")
    result = FunnelResult("candidate-1", "trend", "SURVIVOR", 0.8, ())

    snapshot = promote_candidate(result, store=store, audit=audit, actor="human")

    assert snapshot["champion_hash"] == "candidate-1"
    assert store.read("champion").payload["status"] == "CHAMPION"
    assert audit.path.read_text(encoding="utf-8").count("promote") == 1


def test_promotion_rejects_non_survivor(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="SURVIVOR"):
        promote_candidate(
            FunnelResult("candidate-1", "trend", "REJECT", 0.8, ()),
            store=StateFileStore(tmp_path / "state"),
            audit=AuditLog(tmp_path / "audit.jsonl"),
            actor="human",
        )

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, *, actor: str, inputs: dict[str, Any]) -> None:
        if any("token" in str(key).lower() or "secret" in str(key).lower() for key in inputs):
            raise ValueError("secrets cannot be written to audit log")
        record = {
            "event": event,
            "actor": actor,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_hash": content_hash(inputs),
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

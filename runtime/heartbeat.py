from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class WorkerHeartbeatStore:
    _SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, root: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def record(
        self,
        worker_id: str,
        *,
        job_id: str | None,
        role: str,
        status: str,
        attempt: int = 0,
    ) -> None:
        if not self._SAFE_ID.fullmatch(worker_id):
            raise ValueError("worker_id contains unsafe characters")
        if attempt < 0:
            raise ValueError("attempt cannot be negative")
        payload = {
            "worker_id": worker_id,
            "job_id": job_id,
            "role": role,
            "status": status,
            "last_heartbeat": self._clock().astimezone(timezone.utc).isoformat(),
            "attempt": attempt,
        }
        target = self.root / f"{worker_id}.json"
        temporary = self.root / f".{worker_id}.tmp"
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, target)

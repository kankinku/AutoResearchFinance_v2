from __future__ import annotations

from dataclasses import dataclass

from finance_autoresearch.state.repository import StateRepository


@dataclass(slots=True)
class WorkerHeartbeat:
    state_store: StateRepository
    worker_name: str

    def touch(self) -> None:
        self.state_store.record_heartbeat(self.worker_name)  # type: ignore[arg-type]

    def clear(self) -> None:
        self.state_store.clear_heartbeat(self.worker_name)  # type: ignore[arg-type]

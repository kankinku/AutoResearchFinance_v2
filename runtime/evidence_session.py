"""Bind retries and final generations to one independent research run."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore


class EvidenceSession:
    def __init__(
        self,
        state_dir: Path,
        *,
        requested_generations: int,
        seed: int,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.run_id = uuid4().hex
        self.store = EvidenceStore(state_dir)
        self.store.append(
            "run",
            f"run:{self.run_id}",
            {
                "research_run_id": self.run_id,
                "requested_generations": requested_generations,
                "seed": seed,
                "settings": settings or {},
            },
        )

    def evaluate(
        self, runner: Callable[..., dict[str, object]], **kwargs: Any
    ) -> dict[str, object]:
        attempt_id = uuid4().hex
        identity = {
            "research_run_id": self.run_id,
            "attempt_id": attempt_id,
            "generation": kwargs["generation"],
            "seed": kwargs.get("seed"),
        }
        try:
            result = runner(**kwargs, research_run_id=self.run_id, attempt_id=attempt_id)
        except EvidenceIntegrityError:
            raise
        except Exception as exc:
            self.store.append(
                "attempt",
                f"attempt:{attempt_id}",
                {
                    **identity,
                    "status": "FAILED",
                    "error_class": type(exc).__name__,
                    "candidates": [],
                },
            )
            raise
        existing = any(e["id"] == f"attempt:{attempt_id}" for e in self.store.events())
        if not existing:
            # Dependency-injected evaluators may return aggregate counts, which do not
            # constitute verified candidate evidence or a comparable manifest.
            self.store.append(
                "attempt",
                f"attempt:{attempt_id}",
                {
                    **identity,
                    "status": "COMPLETED",
                    "candidates": [],
                    "verification": "UNVERIFIED_EVALUATOR",
                },
            )
        return {**result, "research_run_id": self.run_id, "attempt_id": attempt_id}

    def finish_generation(
        self, generation: int, status: str, result: dict[str, object] | None
    ) -> None:
        self.store.append(
            "generation",
            f"generation:{self.run_id}:{generation}",
            {
                "research_run_id": self.run_id,
                "generation": generation,
                "status": status,
                "attempt_id": result.get("attempt_id") if result else None,
            },
        )

    def finish_run(self, status: str) -> None:
        self.store.append(
            "end",
            f"end:{self.run_id}",
            {
                "research_run_id": self.run_id,
                "status": status,
            },
        )

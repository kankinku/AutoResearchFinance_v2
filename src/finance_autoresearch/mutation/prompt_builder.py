from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


TaskKind = Literal["mutation", "analysis"]
ExpectedSchema = Literal["mutation_artifact", "analysis_artifact"]

MUTABLE_STRATEGY_TARGET_PATH = (
    "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"
)


@dataclass(slots=True, frozen=True)
class OpenClawRequest:
    task_kind: TaskKind
    run_id: str
    iteration: int
    stage: str
    idempotency_key: str
    agent_id: str
    target_path: str | None
    context: dict[str, Any]
    expected_schema: ExpectedSchema

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_kind": self.task_kind,
            "run_id": self.run_id,
            "iteration": self.iteration,
            "stage": self.stage,
            "idempotency_key": self.idempotency_key,
            "agent_id": self.agent_id,
            "target_path": self.target_path,
            "context": dict(self.context),
            "expected_schema": self.expected_schema,
        }


def build_idempotency_key(run_id: str, iteration: int, stage: str) -> str:
    return f"{run_id}:{iteration}:{stage}"


def build_mutation_request(
    *,
    run_id: str,
    iteration: int,
    stage: str,
    agent_id: str,
    context: dict[str, Any],
    target_path: str = MUTABLE_STRATEGY_TARGET_PATH,
) -> OpenClawRequest:
    return OpenClawRequest(
        task_kind="mutation",
        run_id=run_id,
        iteration=iteration,
        stage=stage,
        idempotency_key=build_idempotency_key(run_id, iteration, stage),
        agent_id=agent_id,
        target_path=target_path,
        context=dict(context),
        expected_schema="mutation_artifact",
    )


def build_analysis_request(
    *,
    run_id: str,
    iteration: int,
    stage: str,
    agent_id: str,
    context: dict[str, Any],
) -> OpenClawRequest:
    return OpenClawRequest(
        task_kind="analysis",
        run_id=run_id,
        iteration=iteration,
        stage=stage,
        idempotency_key=build_idempotency_key(run_id, iteration, stage),
        agent_id=agent_id,
        target_path=None,
        context=dict(context),
        expected_schema="analysis_artifact",
    )

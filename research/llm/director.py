from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.features.contracts import FeatureProposal


class IntentProvider(Protocol):
    def propose(self, context: dict[str, Any]) -> dict[str, Any]: ...


class ResearchIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["structure", "parameter", "mixed"]
    parent_ids: tuple[str, ...] = Field(min_length=1)
    operations: tuple[dict[str, Any], ...] = ()
    rationale: str = Field(min_length=1)
    primitive_request: dict[str, Any] | None = None
    feature_proposal: FeatureProposal | None = None
    python_patch: str | None = None
    evaluator_change: str | None = None

    @model_validator(mode="after")
    def reject_code_changes(self) -> ResearchIntent:
        if self.python_patch is not None or self.evaluator_change is not None:
            raise ValueError("forbidden research intent field: code/evaluator change")
        return self


class ResearchDirector:
    def __init__(self, provider: IntentProvider) -> None:
        self.provider = provider

    def propose(self, context: dict[str, Any]) -> ResearchIntent:
        return ResearchIntent.model_validate(self.provider.propose(context))

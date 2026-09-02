from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.features.contracts import FeatureProposal


class IntentProvider(Protocol):
    def propose(self, context: dict[str, Any]) -> dict[str, Any]: ...


class FeatureSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    inputs: tuple[str, ...] = ()
    timeframe: Literal["1m", "5m", "15m", "1h", "1d", "1w", "1mo"] = "1d"
    lag_bars: int = Field(default=0, ge=0)
    lookback: int | None = Field(default=None, gt=0)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)


class ResearchIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["structure", "parameter", "mixed"]
    parent_ids: tuple[str, ...] = Field(min_length=1)
    operations: tuple[dict[str, Any], ...] = ()
    rationale: str = Field(min_length=1)
    feature_selections: tuple[FeatureSelection, ...] = ()
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

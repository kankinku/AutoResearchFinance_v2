from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.features.contracts import FeatureProposal
from strategy_ir.schema import Condition, FeatureRef, IndicatorSpec


class IntentProvider(Protocol):
    def propose(self, context: dict[str, Any]) -> dict[str, Any]: ...


class IntentRepairUnavailable(ValueError):
    """Raised when the configured provider cannot repair an intent."""


IntentOperationName = Literal[
    "RETAIN",
    "SET_PARAMETER",
    "ADD_RULE",
    "REPLACE_RULE",
    "REMOVE_RULE",
    "ADD_INDICATOR",
    "REMOVE_INDICATOR",
    "SWAP_INDICATOR",
    "ADD_FEATURE",
    "REMOVE_FEATURE",
    "ADD_REGIME_FILTER",
    "REMOVE_REGIME_FILTER",
    "ENABLE_RULE",
    "DISABLE_RULE",
    "CHANGE_AND_OR",
    "CHANGE_STOP",
    "CHANGE_TAKE_PROFIT",
    "CHANGE_TRAILING_STOP",
    "CHANGE_POSITION_SIZE",
]


class IntentOperation(BaseModel):
    """Strict operation envelope returned by Codex and consumed by the bridge."""

    model_config = ConfigDict(extra="forbid")

    op: IntentOperationName
    path: str | None = None
    value: int | float | str | bool | None = None
    condition: Condition | None = None
    feature: FeatureRef | None = None
    indicator: IndicatorSpec | None = None
    logic: Literal["AND", "OR"] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_patch(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        payload = dict(value)
        raw_op = payload.get("op")
        if not isinstance(raw_op, str):
            return payload
        lowered = raw_op.lower()
        if lowered not in {"add", "replace", "remove", "retain"}:
            return payload
        if lowered == "retain":
            if len(payload) == 1:
                return {"op": "RETAIN"}
            return {"op": "RETAIN", "path": payload.get("path"), "value": payload.get("value")}
        path = _legacy_path(payload.get("path"))
        raw_value = _decode_legacy_value(payload.get("value"))
        if lowered == "add":
            if path.startswith("regime_filters"):
                return {"op": "ADD_REGIME_FILTER", "path": "regime_filters", "condition": raw_value}
            if path.endswith(".conditions"):
                return {"op": "ADD_RULE", "path": path, "condition": raw_value}
            if path.startswith("features."):
                return {"op": "ADD_FEATURE", "path": path, "feature": raw_value}
            if path.startswith("indicators."):
                return {"op": "ADD_INDICATOR", "path": path, "indicator": raw_value}
            return {"op": "ADD_RULE", "path": path, "value": raw_value}
        if lowered == "remove":
            if path.startswith("features."):
                return {"op": "REMOVE_FEATURE", "path": path}
            if path.startswith("indicators."):
                return {"op": "REMOVE_INDICATOR", "path": path}
            return {"op": "REMOVE_RULE", "path": path}
        if path.startswith("indicators.") and (
            path.endswith(".period") or ".parameters." in path
        ):
            return {"op": "SET_PARAMETER", "path": path, "value": raw_value}
        if path.endswith(".conditions") or ".conditions." in path:
            return {"op": "REPLACE_RULE", "path": path, "condition": raw_value}
        return {"op": "REPLACE_RULE", "path": path, "value": raw_value}

    @model_validator(mode="after")
    def validate_payload(self) -> IntentOperation:
        if self.op == "RETAIN":
            if any(
                item is not None
                for item in (
                    self.path,
                    self.value,
                    self.condition,
                    self.feature,
                    self.indicator,
                    self.logic,
                )
            ):
                raise ValueError("RETAIN operation cannot carry a target or value")
        elif self.op in {"ADD_RULE", "ADD_REGIME_FILTER"}:
            if self.condition is None:
                raise ValueError(f"{self.op} operation requires a condition object")
            if (
                self.value is not None
                or self.feature is not None
                or self.indicator is not None
                or self.logic is not None
            ):
                raise ValueError(f"{self.op} operation cannot carry an untyped value")
        elif self.op == "REPLACE_RULE":
            if self.condition is not None and self.value is not None:
                raise ValueError("REPLACE_RULE cannot carry both condition and value")
            if self.feature is not None or self.indicator is not None or self.logic is not None:
                raise ValueError("REPLACE_RULE cannot carry an unrelated typed value")
        elif self.op == "ADD_FEATURE":
            if self.feature is None:
                raise ValueError("ADD_FEATURE operation requires a feature object")
            if (
                self.value is not None
                or self.condition is not None
                or self.indicator is not None
                or self.logic is not None
            ):
                raise ValueError("ADD_FEATURE operation cannot carry an untyped value")
        elif self.op == "ADD_INDICATOR":
            if self.indicator is None:
                raise ValueError("ADD_INDICATOR operation requires an indicator object")
            if (
                self.value is not None
                or self.condition is not None
                or self.feature is not None
                or self.logic is not None
            ):
                raise ValueError("ADD_INDICATOR operation cannot carry an untyped value")
        elif self.op == "CHANGE_AND_OR":
            if self.logic is None:
                raise ValueError("CHANGE_AND_OR operation requires logic")
            if (
                self.value is not None
                or self.condition is not None
                or self.feature is not None
                or self.indicator is not None
            ):
                raise ValueError("CHANGE_AND_OR operation cannot carry an untyped value")
        elif self.op in {
            "REMOVE_RULE",
            "REMOVE_FEATURE",
            "REMOVE_INDICATOR",
            "REMOVE_REGIME_FILTER",
            "ENABLE_RULE",
            "DISABLE_RULE",
        }:
            if (
                self.value is not None
                or self.condition is not None
                or self.feature is not None
                or self.indicator is not None
                or self.logic is not None
            ):
                raise ValueError(f"{self.op} operation cannot carry a value")
        return self


def _legacy_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("legacy operation path must be a string")
    if not value.startswith("/"):
        return value[:-2] if value.endswith(".-") else value
    parts = value.lstrip("/").split("/")
    if parts and parts[0] == "source_strategy":
        parts = parts[1:]
    if not parts or any(
        not part or (part == "-" and index != len(parts) - 1)
        for index, part in enumerate(parts)
    ):
        raise ValueError(f"invalid legacy operation path: {value}")
    decoded = [part.replace("~1", "/").replace("~0", "~") for part in parts]
    path = ".".join(decoded)
    return path[:-2] if path.endswith(".-") else path


def _decode_legacy_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped.startswith(("{", "[")):
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


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
    operations: tuple[IntentOperation, ...] = ()
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

    def repair(
        self,
        context: dict[str, Any],
        invalid_intent: dict[str, Any] | None,
        error: str,
    ) -> ResearchIntent:
        repair = getattr(self.provider, "repair", None)
        if not callable(repair):
            raise IntentRepairUnavailable("configured provider has no repair capability")
        payload = repair(dict(context), invalid_intent, error)
        if not isinstance(payload, dict):
            raise ValueError("intent repair response must be a mapping")
        return ResearchIntent.model_validate(payload)

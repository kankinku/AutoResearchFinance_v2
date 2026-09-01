from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = ""
    source_hash: str = ""
    source_type: str = "structured"


class IndicatorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    period: int | None = Field(default=None, gt=0)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: str = Field(min_length=1)
    left: str = Field(min_length=1)
    right: str | None = None
    value: float | int | str | bool | None = None
    enabled: bool = True


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logic: Literal["AND", "OR"]
    conditions: list[Condition] = Field(default_factory=list)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_loss_pct: float = Field(ge=0.0)
    take_profit_pct: float = Field(ge=0.0)
    trailing_stop_pct: float | None = Field(default=None, ge=0.0)
    position_size_pct: float = Field(default=100.0, gt=0.0, le=100.0)


class ResearchMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutation: list[str] = Field(default_factory=list)
    parent_score: float | None = None


class StrategyIR(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: int = Field(gt=0)
    strategy_id: str = Field(alias="id", min_length=1)
    family: str = Field(min_length=1)
    generation: int = Field(ge=0)
    parents: list[str] = Field(default_factory=list)
    indicators: dict[str, IndicatorSpec] = Field(min_length=1)
    entry: RuleSet
    exit: RuleSet
    regime_filters: list[Condition] = Field(default_factory=list)
    risk: RiskConfig
    research: ResearchMetadata = Field(default_factory=ResearchMetadata)
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="before")
    @classmethod
    def unwrap_strategy_document(cls, value: object) -> object:
        if isinstance(value, dict) and "strategy" in value:
            nested = value["strategy"]
            if not isinstance(nested, dict):
                return value
            merged = dict(nested)
            if "schema_version" in value and "schema_version" not in merged:
                merged["schema_version"] = value["schema_version"]
            return merged
        return value

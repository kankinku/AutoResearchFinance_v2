from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ConditionOperator = Literal[
    "cross_above",
    "cross_below",
    "less_than",
    "less_equal",
    "greater_than",
    "greater_equal",
    "equal",
]

IndicatorType = Literal[
    "SMA",
    "EMA",
    "WMA",
    "HMA",
    "DEMA",
    "TEMA",
    "KAMA",
    "WILDER",
    "RSI",
    "MACD",
    "ATR",
    "ADX",
    "BOLLINGER",
    "IBS",
    "DISPARITY",
    "CONSECUTIVE",
    "VOLATILITY_IND",
    "CHANGE",
    "MAXIMUM",
    "ROC",
    "VOLUME_BREAKOUT",
    "52_WEEK_HIGH",
    "VOLATILITY_FILTER",
    "REGIME_FILTER",
]

_CONDITION_OPERATOR_ALIASES = {
    "gt": "greater_than",
    "gte": "greater_equal",
    "ge": "greater_equal",
    "lt": "less_than",
    "lte": "less_equal",
    "le": "less_equal",
    "eq": "equal",
}

_INDICATOR_TYPE_ALIASES = {
    "HIGHEST": "MAXIMUM",
}


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = ""
    source_hash: str = ""
    source_type: str = "structured"


class IndicatorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: IndicatorType
    period: int | None = Field(default=None, gt=0)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_verified_type(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        return _INDICATOR_TYPE_ALIASES.get(normalized, normalized)


class FeatureRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str = Field(min_length=1)
    timeframe: Literal["1m", "5m", "15m", "1h", "1d", "1w", "1mo"] = "1d"
    lag_bars: int = Field(default=0, ge=0)
    lookback: int | None = Field(default=None, gt=0)
    inputs: tuple[str, ...] = ()
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: ConditionOperator
    left: str = Field(min_length=1)
    right: str | None = None
    value: float | int | str | bool | None = None
    enabled: bool = True

    @field_validator("op", mode="before")
    @classmethod
    def normalize_verified_operator(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        return _CONDITION_OPERATOR_ALIASES.get(normalized, normalized)

    @field_validator("left", "right", mode="before")
    @classmethod
    def normalize_reference_alias(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        for prefix in ("features.", "indicators."):
            if value.startswith(prefix):
                return value.removeprefix(prefix)
        return value


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
    risk_appetite: float | None = Field(default=None, ge=0.0, le=1.0)
    loss_tolerance_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    daily_loss_limit_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    daily_loss_action: Literal["none", "reduce", "hold", "stop"] = "none"
    max_concurrent_positions: int | None = Field(default=None, gt=0)
    max_total_exposure_pct: float | None = Field(default=None, gt=0.0, le=100.0)


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
    features: dict[str, FeatureRef] = Field(default_factory=dict)
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

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeatureContractError(ValueError):
    """Raised when a feature definition is not safe to calculate."""


class FeatureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    family: str = Field(min_length=1)
    inputs: tuple[str, ...] = Field(min_length=1)
    calculator: str = Field(default="expression", min_length=1)
    timeframe: str = "1d"
    lookback: int = Field(gt=0)
    lag_bars: int = Field(default=0, ge=0)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)
    formula: str = Field(min_length=1)
    output_type: Literal["float", "boolean"] = "float"
    version: str = "feature-v1"
    status: Literal["PROPOSED", "REGISTERED", "QUARANTINED"] = "PROPOSED"
    implementation_hash: str = ""

    @field_validator("inputs")
    @classmethod
    def reject_empty_inputs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("feature inputs cannot be empty")
        if len(value) != len(set(value)):
            raise ValueError("feature inputs must be unique")
        return value

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        if value not in {"1m", "5m", "15m", "1h", "1d", "1w", "1mo"}:
            raise ValueError("unsupported feature timeframe")
        return value


class FeatureVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_valid: bool = False
    unit: bool = False
    historical: bool = False
    no_future_leak: bool = False
    alignment: bool = False
    missing_data: bool = False
    reproducible: bool = False
    resource_bounded: bool = False
    safe: bool = False

    @property
    def passed(self) -> bool:
        return all(self.model_dump().values())


class FeatureProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    family: str = Field(min_length=1)
    inputs: tuple[str, ...] = Field(min_length=1)
    calculator: str = Field(default="expression", min_length=1)
    timeframe: str = "1d"
    lookback: int = Field(gt=0)
    lag_bars: int = Field(default=0, ge=0)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)
    formula: str = Field(min_length=1)
    justification: str = Field(min_length=1)

    @field_validator("formula")
    @classmethod
    def reject_executable_formula(cls, value: str) -> str:
        forbidden = ("import ", "exec(", "eval(", "requests", "open(", "submit_order")
        if any(fragment in value.lower() for fragment in forbidden):
            raise ValueError("unsafe executable feature formula")
        return value

    def to_spec(self) -> FeatureSpec:
        return FeatureSpec(
            name=self.name,
            family=self.family,
            inputs=self.inputs,
            calculator=self.calculator,
            timeframe=self.timeframe,
            lookback=self.lookback,
            lag_bars=self.lag_bars,
            parameters=self.parameters,
            formula=self.formula,
        )

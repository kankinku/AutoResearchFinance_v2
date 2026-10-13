"""Immutable academic sources and gated, non-tradable research signal metadata."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SignalRole = Literal["entry", "regime", "risk"]
SignalScope = Literal["single_asset", "cross_section"]
SignalStatus = Literal["PROPOSED", "VERIFIED", "QUARANTINED"]
Calculator = Literal[
    "sma_direction",
    "time_series_momentum",
    "garman_klass_variance",
    "previous_range_breakout",
    "cross_sectional_momentum",
]

DOI_PATTERN = re.compile(r"^10\.[0-9]{4,9}/[-._;()/:A-Za-z0-9]+$")
CANONICAL_FORMULAS: dict[str, str] = {
    "sma_direction": "close[t] > mean(close[t-n+1:t+1]); signal at close[t] for next bar",
    "time_series_momentum": "close[t] / close[t-n] - 1 > 0; next-bar signal",
    "garman_klass_variance": ("mean(0.5*ln(high/low)^2 - (2*ln(2)-1)*ln(close/open)^2, n)"),
    "previous_range_breakout": "close[t] > max(high[t-n:t]); next-bar signal",
    "cross_sectional_momentum": (
        "rank each asset's lagged momentum within point-in-time tradable universe"
    ),
}


class CitationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    count: int = Field(ge=0)
    provider: str = Field(min_length=1)
    observed_on: date

    @field_validator("provider")
    @classmethod
    def no_blank_provider(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("citation provider is required")
        return value


class Paper(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    doi: str
    title: str = Field(min_length=1)
    authors: tuple[str, ...] = Field(min_length=1)
    published_year: int = Field(ge=1900, le=2100)
    source_url: str
    venue: str = Field(min_length=1)
    source_scope: str = Field(min_length=1)
    replication_note: str = Field(min_length=1)
    citation_snapshot: CitationSnapshot | None = None

    @field_validator("doi")
    @classmethod
    def valid_doi(cls, value: str) -> str:
        normalized = value.strip().lower()
        if DOI_PATTERN.fullmatch(normalized) is None:
            raise ValueError("invalid DOI")
        return normalized

    @model_validator(mode="after")
    def known_official_link(self) -> Paper:
        if self.source_url.lower() != f"https://doi.org/{self.doi}":
            raise ValueError("source_url must use exact official DOI resolver")
        if any(not author.strip() for author in self.authors):
            raise ValueError("blank authors not allowed")
        return self


class IndicatorCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    paper_doi: str
    calculator: Calculator
    family: str = Field(min_length=1)
    role: SignalRole
    required_fields: tuple[str, ...] = Field(min_length=1)
    lookback: int = Field(ge=2, le=500)
    formula: str
    scope: SignalScope
    status: SignalStatus = "PROPOSED"
    sample_frequency: Literal["1d"] = "1d"
    execution_delay_bars: Literal[1] = 1

    @field_validator("paper_doi")
    @classmethod
    def valid_paper_doi(cls, value: str) -> str:
        return Paper.valid_doi(value)

    @model_validator(mode="after")
    def enforce_math_mapping(self) -> IndicatorCandidate:
        if self.formula != CANONICAL_FORMULAS[self.calculator]:
            raise ValueError("formula differs from approved, reviewed calculator definition")
        requires = {
            "sma_direction": {"close"},
            "time_series_momentum": {"close"},
            "garman_klass_variance": {"open", "high", "low", "close"},
            "previous_range_breakout": {"high", "close"},
            "cross_sectional_momentum": {"close"},
        }[self.calculator]
        if set(self.required_fields) != requires or len(self.required_fields) != len(requires):
            raise ValueError("calculator input contract does not match required fields")
        if self.calculator == "garman_klass_variance" and self.role != "risk":
            raise ValueError("variance estimator must be a risk filter")
        if self.calculator == "cross_sectional_momentum":
            if self.scope != "cross_section":
                raise ValueError("cross-sectional returns require a multi-asset dataset")
        elif self.scope != "single_asset":
            raise ValueError("single-asset indicator cannot become cross-sectional")
        return self


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_hash: str = Field(min_length=64, max_length=64)
    passed: bool
    math_reference: bool
    causal_prefix: bool
    missing_data: bool
    deterministic: bool
    bounded: bool
    error: str | None = None


class ResearchHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_ids: tuple[str, ...] = Field(min_length=2, max_length=3)
    roles: tuple[SignalRole, ...] = Field(min_length=2, max_length=3)
    identity_hash: str = Field(min_length=64, max_length=64)
    status: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    executable: Literal[False] = False
    sealed_oos_approved: Literal[False] = False

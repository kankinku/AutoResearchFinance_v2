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
    "parkinson_variance",
    "volatility_managed_exposure",
    "sma_pullback",
    "dual_sma_trend",
    "ema_direction",
    "range_low_reclaim",
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
    "parkinson_variance": "mean(ln(high/low)^2 / (4*ln(2)), n)",
    "volatility_managed_exposure": (
        "min(max_exposure, target_daily_variance / mean(ln(close[t-k]/close[t-k-1])^2,k=0:n-1)); "
        "known after close[t], apply at next bar; cash-only, no leverage"
    ),
    "sma_pullback": "close[t] < mean(close[t-n+1:t+1]); next open only",
    "dual_sma_trend": "mean(close[t-floor(n/4)+1:t+1]) > mean(close[t-n+1:t+1]); next open",
    "ema_direction": (
        "close[t] > EMA_n[t]; EMA seeded mean(close[0:n]), "
        "alpha=2/(n+1), emit from t=n-1; next open"
    ),
    "range_low_reclaim": (
        "low[t] < min(low[t-n:t]) and close[t] > min(low[t-n:t]); next open"
    ),
}

# These rules emit a binary long-entry vote, not an execution instruction.
BINARY_ENTRY_CALCULATORS = frozenset({
    "time_series_momentum", "previous_range_breakout",
    "sma_pullback", "dual_sma_trend", "ema_direction", "range_low_reclaim",
})


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
    target_daily_variance: float | None = Field(default=None, ge=1e-8, le=0.05, allow_inf_nan=False)
    max_exposure: float | None = Field(default=None, ge=0.05, le=1.0, allow_inf_nan=False)

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
            "parkinson_variance": {"high", "low"},
            "volatility_managed_exposure": {"close"},
            "sma_pullback": {"close"},
            "dual_sma_trend": {"close"},
            "ema_direction": {"close"},
            "range_low_reclaim": {"low", "close"},
        }[self.calculator]
        if set(self.required_fields) != requires or len(self.required_fields) != len(requires):
            raise ValueError("calculator input contract does not match required fields")
        if (
            self.calculator
            in {"garman_klass_variance", "parkinson_variance", "volatility_managed_exposure"}
            and self.role != "risk"
        ):
            raise ValueError("variance estimators and exposure controls must be risk features")
        if self.calculator == "volatility_managed_exposure":
            if self.target_daily_variance is None or self.max_exposure is None:
                raise ValueError("ex-ante daily variance target and exposure cap required")
        elif self.target_daily_variance is not None or self.max_exposure is not None:
            raise ValueError("exposure-control parameters cannot alter other calculators")
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

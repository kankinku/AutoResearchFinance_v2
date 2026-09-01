from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class PolicyError(ValueError):
    """Raised when a research policy is invalid or cannot be loaded."""


class SearchPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_ratio: float = Field(ge=0.0, le=1.0)
    explore_ratio: float = Field(ge=0.0, le=1.0)
    crossover_ratio: float = Field(ge=0.0, le=1.0)
    rescue_ratio: float = Field(ge=0.0, le=1.0)
    candidate_target: int = Field(gt=0)
    methods: list[str] = Field(min_length=1)

    @property
    def total_ratio(self) -> float:
        return self.exploit_ratio + self.explore_ratio + self.crossover_ratio + self.rescue_ratio


class EvaluationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fast_screen: bool
    full_backtest: bool
    robustness: bool
    validation: bool
    min_trade_count: int = Field(ge=0)


class RuntimePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(ge=0)
    job_timeout_seconds: int = Field(gt=0)
    max_concurrency: int = Field(gt=0)


class LLMPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_on_generation_start: bool
    call_on_plateau: bool
    call_on_new_family: bool
    call_on_new_primitive: bool


class DeploymentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    live_order_permission: str
    human_approval_required: bool


class ResearchPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(gt=0)
    data_zones: dict[str, str]
    search: SearchPolicy
    evaluation: EvaluationPolicy
    runtime: RuntimePolicy
    llm: LLMPolicy
    deployment: DeploymentPolicy


def load_policy(path: Path) -> ResearchPolicy:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        policy = ResearchPolicy.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError, TypeError) as exc:
        raise PolicyError(f"invalid policy: {exc}") from exc
    if abs(policy.search.total_ratio - 1.0) > 1e-9:
        raise PolicyError("search allocation ratios must sum to 1")
    if policy.deployment.live_order_permission != "deny":
        raise PolicyError("live order permission must default to deny")
    return policy

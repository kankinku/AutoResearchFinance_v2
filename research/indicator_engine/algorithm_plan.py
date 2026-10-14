"""S3: bounded, typed LLM algorithm plans over already verified academic indicators.

This is research-only. A deterministic compiler lowers weighted voting and
ordered market-regime branches to binary feature vectors consumed by the
unchanged canonical StrategyIR backtest. No runtime Python/DSL evaluation,
orders, leverage, dynamic portfolio sizing or permission to inspect sealed OOS.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.bridge import ResearchSignalReplay
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.decision_audit import (
    AcademicDecisionAudit,
    audit_compiled_academic_decisions,
)
from research.indicator_engine.models import BINARY_ENTRY_CALCULATORS
from research.indicator_engine.signals import calculate_signal
from research.indicator_engine.strategy_adapter import (
    AcademicDevelopmentResult,
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)
from strategy_ir.schema import StrategyIR

_RESERVED = frozenset({"plan_entry", "plan_regime", "plan_branch_index", "plan_vote_score"})


class IndicatorGate(BaseModel):
    """A completed-close gate with no lookahead operator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    indicator_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    op: Literal["greater_than", "less_equal"]
    threshold: float = Field(allow_inf_nan=False)


class WeightedVote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    indicator_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    weight: float = Field(gt=0, le=10, allow_inf_nan=False)


class RegimeCase(BaseModel):
    """First satisfied case wins; its positive voting score triggers a long entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    when: IndicatorGate
    votes: tuple[WeightedVote, ...] = Field(min_length=1, max_length=8)
    min_score: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def no_duplicate_votes(self) -> RegimeCase:
        names = [vote.indicator_id for vote in self.votes]
        if len(set(names)) != len(names):
            raise ValueError("duplicate indicator in a regime vote")
        return self


class AlgorithmPlan(BaseModel):
    """An LLM-authorable plan that cannot carry code or unregistered primitives.

    `weight` controls INDICATOR VOTES, not position exposure; only a fixed
    fully funded 100% research allocation is supported by this v1 compiler.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    cases: tuple[RegimeCase, ...] = Field(min_length=1, max_length=8)
    unmatched: Literal["FLAT"] = "FLAT"
    position_size_pct: Literal[100] = 100

    @model_validator(mode="after")
    def no_duplicate_cases(self) -> AlgorithmPlan:
        names = [case.case_id for case in self.cases]
        if len(set(names)) != len(names):
            raise ValueError("duplicate regime case id")
        return self


@dataclass(frozen=True)
class CompiledAlgorithmPlan:
    plan: AlgorithmPlan
    plan_hash: str
    definitions_hash: str
    compiled: CompiledAcademicStrategy
    status: Literal["NON_PIT_ALGORITHM_DEVELOPMENT_ONLY"] = (
        "NON_PIT_ALGORITHM_DEVELOPMENT_ONLY"
    )
    sealed_oos_approved: Literal[False] = False
    broker_executable: Literal[False] = False

    @property
    def algorithm(self) -> CompiledAcademicStrategy:
        return self.compiled


def _source_names(plan: AlgorithmPlan) -> tuple[str, ...]:
    return tuple(sorted({
        name
        for case in plan.cases
        for name in (case.when.indicator_id, *(vote.indicator_id for vote in case.votes))
    }))


def _plan_vectors(
    plan: AlgorithmPlan,
    sources: dict[str, tuple[float | None, ...]],
    width: int,
) -> dict[str, tuple[float | None, ...]]:
    entries: list[float | None] = []
    regime: list[float | None] = []
    branch: list[float | None] = []
    scores: list[float | None] = []
    for t in range(width):
        selected: tuple[int, RegimeCase] | None = None
        incomplete = False
        for index, case in enumerate(plan.cases, start=1):
            observed = sources[case.when.indicator_id][t]
            if observed is None:
                incomplete = True
                break
            if not isfinite(observed):
                raise ResearchCatalogError("nonfinite regime source observation")
            matched = (
                observed > case.when.threshold if case.when.op == "greater_than"
                else observed <= case.when.threshold
            )
            if matched:
                selected = index, case
                break
        if incomplete:
            entries.append(None)
            regime.append(None)
            branch.append(None)
            scores.append(None)
        elif selected is None:
            entries.append(0.0)
            regime.append(0.0)
            branch.append(0.0)
            scores.append(0.0)
        else:
            index, case = selected
            values = [sources[vote.indicator_id][t] for vote in case.votes]
            if any(value is None for value in values):
                entries.append(None)
                regime.append(None)
                branch.append(None)
                scores.append(None)
                continue
            if any(value not in (0.0, 1.0) for value in values):
                raise ResearchCatalogError("non-binary academic entry signal")
            denom = sum(vote.weight for vote in case.votes)
            complete_values = [float(value) for value in values if value is not None]
            score = sum(
                (vote.weight * value
                 for vote, value in zip(case.votes, complete_values, strict=True)),
                0.0,
            ) / denom
            entries.append(float(score >= case.min_score))
            regime.append(1.0)
            branch.append(float(index))
            scores.append(score)
    return {
        "plan_entry": tuple(entries),
        "plan_regime": tuple(regime),
        "plan_branch_index": tuple(branch),
        "plan_vote_score": tuple(scores),
    }


def compile_algorithm_plan(
    catalog: ResearchCatalog,
    plan: AlgorithmPlan,
    market: MarketDataSet,
) -> CompiledAlgorithmPlan:
    """Compile exclusively catalog-VERIFIED, causal, single-asset academic signals."""
    if not isinstance(plan, AlgorithmPlan):
        raise ResearchCatalogError("typed AlgorithmPlan is required")
    # model_copy() skips Pydantic validation; reject even forged in-memory plans.
    try:
        plan = AlgorithmPlan.model_validate(plan.model_dump(mode="json"))
    except ValidationError as exc:
        raise ResearchCatalogError("algorithm plan validation failed") from exc
    if market.zone != DataZone.DEVELOPMENT:
        raise ResearchCatalogError("only development data may compile research algorithms")
    if market.calendar != "us_equities" or market.timeframe != "1d":
        raise ResearchCatalogError("reviewed academic plan requires US equities 1d")
    if not 2 <= len(market.bars) <= 1_000_000 or len({b.symbol for b in market.bars}) != 1:
        raise ResearchCatalogError("single-asset bounded research data required")
    source_names = _source_names(plan)
    if any(name in _RESERVED for name in source_names):
        raise ResearchCatalogError("algorithm plan alias collision")
    definitions = {}
    gate_names = {case.when.indicator_id for case in plan.cases}
    vote_names = {vote.indicator_id for case in plan.cases for vote in case.votes}
    for name in source_names:
        candidate = catalog.get_indicator(name)
        if candidate.status != "VERIFIED":
            raise ResearchCatalogError("only VERIFIED research indicators may execute")
        if candidate.scope != "single_asset" or candidate.execution_delay_bars != 1:
            raise ResearchCatalogError("unsupported PIT or execution lag for academic indicator")
        if name in vote_names and (
            candidate.role != "entry" or candidate.calculator not in BINARY_ENTRY_CALCULATORS
        ):
            raise ResearchCatalogError("votes require reviewed binary entry indicators")
        if name in gate_names and candidate.role not in ("regime", "risk"):
            raise ResearchCatalogError("regime gates require verified regime or risk indicators")
        definitions[name] = candidate

    # All source values are strictly causal, recomputed from the actual bars.
    inputs = {
        key: tuple(float(getattr(bar, key)) for bar in market.bars)
        for key in ("open", "high", "low", "close")
    }
    raw = {name: calculate_signal(definitions[name], inputs) for name in source_names}
    values = {**raw, **_plan_vectors(plan, raw, len(market.bars))}
    signals = tuple((name, values[name]) for name in sorted(values))
    plan_hash = content_hash(plan.model_dump(mode="json"))
    definitions_hash = content_hash(tuple(
        (name, definitions[name].model_dump(mode="json")) for name in source_names
    ))
    hypothesis_hash = content_hash({
        "plan_hash": plan_hash,
        "definitions_hash": definitions_hash,
        "compiler": "academic-typed-branch-weighted-v1",
    })
    timestamps = tuple(bar.timestamp for bar in market.bars)
    next_bar = timestamps[1:] + (None,)
    count = sum(
        values["plan_entry"][i] == 1.0 and values["plan_regime"][i] == 1.0
        for i in range(len(market.bars) - 1)
    )
    replay_hash = content_hash({
        "hypothesis": hypothesis_hash,
        "dataset": market.dataset_hash,
        "signals": signals,
        "decision_timestamps": [t.isoformat() for t in timestamps],
        "earliest_next_bar": [t.isoformat() if t else None for t in next_bar],
        "research_only": True,
    })
    replay = ResearchSignalReplay(
        hypothesis_hash=hypothesis_hash,
        data_hash=market.dataset_hash,
        signals=signals,
        timestamps=timestamps,
        execution_not_before=next_bar,
        entry_regime_observations=count,
        replay_hash=replay_hash,
    )
    features = {
        name: {
            "feature_id": "academic.plan." + name,
            "timeframe": "1d",
            "lag_bars": 0,
            "lookback": (definitions[name].lookback if name in definitions else
                          max(c.lookback for c in definitions.values())),
        }
        for name in values
    }
    ir = StrategyIR.model_validate({
        "schema_version": 1,
        "id": "research_plan_" + hypothesis_hash[:16],
        "family": "academic_algorithm_plan",
        "generation": 0,
        "parents": [],
        "indicators": {"_unused_sma": {"type": "SMA", "period": 2}},
        "features": features,
        "entry": {"logic": "AND", "conditions": [
            {"op": "greater_than", "left": "plan_entry", "value": 0.5}
        ]},
        "exit": {"logic": "OR", "conditions": [
            {"op": "less_equal", "left": "plan_entry", "value": 0.5}
        ]},
        "regime_filters": [{"op": "greater_than", "left": "plan_regime", "value": 0.5}],
        "risk": {"stop_loss_pct": 0.0, "take_profit_pct": 0.0,
                 "position_size_pct": 100.0},
        "provenance": {
            "source_type": "typed-algorithm-plan-non-PIT",
            "source_path": "research.indicator_engine.algorithm_plan",
            "source_hash": content_hash({
                "plan": plan_hash, "definitions": definitions_hash,
                "replay": replay_hash, "compiler": "academic-typed-branch-weighted-v1",
            }),
        },
    })
    compiled = CompiledAcademicStrategy(
        hypothesis_hash=hypothesis_hash,
        dataset_hash=market.dataset_hash,
        replay=replay,
        strategy=ir,
        strategy_hash=content_hash(ir.model_dump(mode="json", by_alias=True)),
        feature_values=values,
    )
    return CompiledAlgorithmPlan(
        plan=plan, plan_hash=plan_hash, definitions_hash=definitions_hash,
        compiled=compiled,
    )


def _verify_and_recompile(
    catalog: ResearchCatalog, compiled: CompiledAlgorithmPlan, market: MarketDataSet,
) -> CompiledAcademicStrategy:
    """Recompute every source independently of caller-provided feature vectors."""
    if compiled.status != "NON_PIT_ALGORITHM_DEVELOPMENT_ONLY":
        raise ResearchCatalogError("algorithm plan research status integrity mismatch")
    fresh = compile_algorithm_plan(catalog, compiled.plan, market)
    if fresh != compiled:
        raise ResearchCatalogError("algorithm plan replay/definition integrity mismatch")
    return fresh.compiled


def evaluate_algorithm_plan(
    catalog: ResearchCatalog, compiled: CompiledAlgorithmPlan,
    market: MarketDataSet, *, initial_cash: float = 10_000.0,
) -> AcademicDevelopmentResult:
    return evaluate_compiled_development(
        _verify_and_recompile(catalog, compiled, market), market, initial_cash=initial_cash
    )


def audit_algorithm_plan(
    catalog: ResearchCatalog, compiled: CompiledAlgorithmPlan,
    market: MarketDataSet, *, initial_cash: float = 10_000.0,
) -> AcademicDecisionAudit:
    return audit_compiled_academic_decisions(
        _verify_and_recompile(catalog, compiled, market), market, initial_cash=initial_cash
    )


class AlgorithmPlanProvider(Protocol):
    """An LLM adapter: returns one bounded, structured AlgorithmPlan object."""

    def propose(self, context: dict[str, Any]) -> dict[str, Any]: ...


def build_algorithm_plan_context(
    catalog: ResearchCatalog, market: MarketDataSet,
) -> dict[str, Any]:
    """Expose only VERIFIED indicators to an external GPT director, no raw prices."""
    if market.zone != DataZone.DEVELOPMENT:
        raise ResearchCatalogError("only development data may reach algorithm plan provider")
    if market.calendar != "us_equities" or market.timeframe != "1d":
        raise ResearchCatalogError("reviewed academic provider supports US equities 1d")
    if not market.bars or len({b.symbol for b in market.bars}) != 1:
        raise ResearchCatalogError("single-asset bounded data required for planning")
    verified = catalog.list_indicators(eligible_only=True)
    eligible = tuple(x for x in verified if (
        x.scope == "single_asset" and x.execution_delay_bars == 1
        and (x.role in {"risk", "regime"} or (
            x.role == "entry" and x.calculator in BINARY_ENTRY_CALCULATORS
        ))
    ))
    context: dict[str, Any] = {
        "output_contract": "AlgorithmPlan",
        "algorithm_plan_schema": AlgorithmPlan.model_json_schema(),
        "verified_indicators": [
            {"indicator_id": x.signal_id, "role": x.role, "calculator": x.calculator,
             "lookback": x.lookback, "definition_hash": content_hash(x.model_dump(mode="json"))}
            for x in eligible
        ],
        "market": {"symbol": market.bars[0].symbol, "data_zone": "DEVELOPMENT",
                   "timeframe": market.timeframe, "calendar": market.calendar},
        "execution_policy": "RESEARCH_ONLY_NEXT_OPEN",
        "indicator_weights_mean": "normalize_positive_votes_to_sum_1",
        "position_sizing": "FIXED_100_PCT_CASH_ONLY",
        "future_data_access": False,
    }
    return context


def compile_provider_algorithm_plan(
    catalog: ResearchCatalog,
    provider: AlgorithmPlanProvider,
    market: MarketDataSet,
) -> CompiledAlgorithmPlan:
    """S3: schema-validated external GPT response to canonical StrategyIR."""
    context = build_algorithm_plan_context(catalog, market)
    try:
        response = provider.propose(deepcopy(context))
        plan = AlgorithmPlan.model_validate(response)
    except ValidationError as exc:
        raise ResearchCatalogError("algorithm provider output validation failed") from exc
    return compile_algorithm_plan(catalog, plan, market)

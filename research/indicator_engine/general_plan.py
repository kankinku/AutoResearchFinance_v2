"""P1-3 opt-in generalized research plan provider: typed, bounded, causal.

Supports compositional expression and state-machine entry/exit algorithms
without Python/Pine execution or edits to the protected strategy backtester.
NOT registered with the operational GPT research loop or MCP tools.
This experimental provider is DEVELOPMENT-only, 1d US equities, long/flat.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.bridge import ResearchSignalReplay
from research.indicator_engine.expression_ir import (
    MAX_BARS,
    Expression,
    ExpressionError,
    compile_expression,
    development_signal_vector,
)
from research.indicator_engine.state_machine_ir import (
    StateMachinePlan,
    compile_state_machine,
    development_state_signal_vector,
    evaluate_state_machine,
)
from research.indicator_engine.strategy_adapter import (
    AcademicDevelopmentResult,
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)
from strategy_ir.schema import StrategyIR

_RAW_SOURCES = ("open", "high", "low", "close", "volume")
_SOURCE_TYPES: dict[str, Literal["number"]] = {name: "number" for name in _RAW_SOURCES}


class GeneralResearchPlanError(ValueError):
    """Candidate does not meet the isolated reviewed research contract."""


class SignalDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["expression", "state_machine"]
    expression: Expression | None = None
    state_machine: StateMachinePlan | None = None

    @model_validator(mode="after")
    def valid_variant(self) -> SignalDefinition:
        if self.kind == "expression":
            if self.expression is None or self.state_machine is not None:
                raise ValueError("expression kind requires only an expression")
        elif self.state_machine is None or self.expression is not None:
            raise ValueError("state_machine kind requires only a state machine")
        return self


class GeneralResearchPlan(BaseModel):
    """Opt-in LLM-authorable algorithm with independently defined entry and exit."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    entry: SignalDefinition
    exit: SignalDefinition
    position_size_pct: Literal[100] = 100


@dataclass(frozen=True)
class CompiledGeneralResearchPlan:
    plan: GeneralResearchPlan
    plan_hash: str
    entry_definition_hash: str
    exit_definition_hash: str
    entry_trace_hash: str | None
    exit_trace_hash: str | None
    compiled: CompiledAcademicStrategy
    status: Literal["NON_PIT_DEVELOPMENT_ONLY"] = "NON_PIT_DEVELOPMENT_ONLY"
    broker_executable: Literal[False] = False
    sealed_oos_approved: Literal[False] = False


def _require_development_market(market: MarketDataSet) -> None:
    if market.zone != DataZone.DEVELOPMENT:
        raise GeneralResearchPlanError("DEVELOPMENT market is required; OOS is forbidden")
    if market.calendar != "us_equities" or market.timeframe != "1d":
        raise GeneralResearchPlanError("only reviewed US equities 1d research is supported")
    if not 2 <= len(market.bars) <= MAX_BARS or len({b.symbol for b in market.bars}) != 1:
        raise GeneralResearchPlanError("bounded single-asset data are required")
    if any(a.timestamp >= b.timestamp for a, b in zip(market.bars, market.bars[1:], strict=False)):
        raise GeneralResearchPlanError("research timestamps must be strictly increasing")


def build_general_plan_context(market: MarketDataSet) -> dict[str, Any]:
    """Output schema and reviewed primitives only, never raw or sealed prices."""
    _require_development_market(market)
    return {
        "output_contract": "GeneralResearchPlan",
        "general_plan_schema": GeneralResearchPlan.model_json_schema(),
        "available_sources": _RAW_SOURCES,
        "market": {
            "symbol": market.bars[0].symbol,
            "data_zone": "DEVELOPMENT",
            "timeframe": market.timeframe,
            "calendar": market.calendar,
        },
        "signal_contract": (
            "Design a boolean expression or finite-state-machine separately for entry "
            "and exit. All observations are known only at completed bar close. "
            "Missing signal values authorize no entry or exit."
        ),
        "execution_policy": "RESEARCH_ONLY_NEXT_OPEN",
        "position_sizing": "FIXED_100_PCT_CASH_ONLY",
        "external_indicator_permission": False,
        "unbounded_code_execution": False,
        "sealed_data_access": False,
    }


def _calculate_signal(
    definition: SignalDefinition,
    market: MarketDataSet,
) -> tuple[tuple[float | None, ...], str, str | None]:
    if definition.kind == "expression":
        assert definition.expression is not None
        compiled = compile_expression(definition.expression, _SOURCE_TYPES)
        if compiled.result_type != "boolean":
            raise GeneralResearchPlanError("entry/exit expression must have boolean output")
        return development_signal_vector(compiled, market), compiled.definition_hash, None

    assert definition.state_machine is not None
    compiled_machine = compile_state_machine(definition.state_machine, _SOURCE_TYPES)
    signal = development_state_signal_vector(compiled_machine, market)
    # Trace is part of evidence even when different internal states produce
    # identical final binary decisions.
    observations = {
        name: tuple(float(getattr(bar, name)) for bar in market.bars)
        for name, _ in compiled_machine.source_types
    }
    trace = evaluate_state_machine(
        compiled_machine,
        observations,
        bar_count=len(market.bars),
    )
    if signal != tuple(float(v) if v is not None else None for v in trace.signals):
        raise GeneralResearchPlanError("state machine replay is inconsistent")
    return signal, compiled_machine.definition_hash, trace.trace_hash


def compile_general_research_plan(
    plan: GeneralResearchPlan | dict[str, Any],
    market: MarketDataSet,
) -> CompiledGeneralResearchPlan:
    """Validate proposed algorithm, derive causal vectors, lower to unchanged IR v1."""
    _require_development_market(market)
    try:
        payload = plan.model_dump(mode="json") if isinstance(plan, GeneralResearchPlan) else plan
        reviewed = GeneralResearchPlan.model_validate(payload)
        entry, entry_definition_hash, entry_trace_hash = _calculate_signal(reviewed.entry, market)
        exit_, exit_definition_hash, exit_trace_hash = _calculate_signal(reviewed.exit, market)
    except (ValidationError, ExpressionError, TypeError, ValueError) as exc:
        raise GeneralResearchPlanError(
            "general plan schema, type or execution validation failed"
        ) from exc

    vectors = {"plan_entry": entry, "plan_exit": exit_}
    plan_hash = content_hash(reviewed.model_dump(mode="json"))
    # Both the program and confirmed data-dependent state trace participate
    # in replay identity; changing a future bar must not rewrite older signals.
    definitions_hash = content_hash(
        {
            "entry": entry_definition_hash,
            "exit": exit_definition_hash,
            "entry_trace": entry_trace_hash,
            "exit_trace": exit_trace_hash,
            "adapter": "p1-3-opt-in-general-research-v1",
        }
    )
    hypothesis_hash = content_hash(
        {
            "plan": plan_hash,
            "definitions": definitions_hash,
            "data": market.dataset_hash,
            "research_only": True,
        }
    )

    stamps = tuple(bar.timestamp for bar in market.bars)
    next_stamps = stamps[1:] + (None,)
    signals = tuple(sorted(vectors.items()))
    replay_body = {
        "hypothesis": hypothesis_hash,
        "dataset": market.dataset_hash,
        "signals": signals,
        "decision_timestamps": [ts.isoformat() for ts in stamps],
        "earliest_next_bar": [ts.isoformat() if ts else None for ts in next_stamps],
        "research_only": True,
    }
    replay = ResearchSignalReplay(
        hypothesis_hash=hypothesis_hash,
        data_hash=market.dataset_hash,
        signals=signals,
        timestamps=stamps,
        execution_not_before=next_stamps,
        entry_regime_observations=sum(value == 1.0 for value in entry[:-1]),
        replay_hash=content_hash(replay_body),
    )
    ir = StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "general_research_" + hypothesis_hash[:16],
            "family": "general_development_plan",
            "generation": 0,
            "parents": [],
            "indicators": {"_unused_sma": {"type": "SMA", "period": 2}},
            "features": {
                name: {
                    "feature_id": "academic.general." + name,
                    "timeframe": "1d",
                    "lag_bars": 0,
                    "lookback": 2,
                }
                for name in vectors
            },
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "plan_entry", "value": 0.5}],
            },
            "exit": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "plan_exit", "value": 0.5}],
            },
            "risk": {"stop_loss_pct": 0.0, "take_profit_pct": 0.0, "position_size_pct": 100.0},
            "provenance": {
                "source_type": "typed-general-development-non-PIT",
                "source_path": "research.indicator_engine.general_plan",
                "source_hash": content_hash(
                    {
                        "plan": plan_hash,
                        "definitions": definitions_hash,
                        "replay": replay.replay_hash,
                    }
                ),
            },
        }
    )
    strategy_hash = content_hash(ir.model_dump(mode="json", by_alias=True))
    compiled = CompiledAcademicStrategy(
        hypothesis_hash=hypothesis_hash,
        dataset_hash=market.dataset_hash,
        replay=replay,
        strategy=ir,
        strategy_hash=strategy_hash,
        feature_values=vectors,
    )
    return CompiledGeneralResearchPlan(
        plan=reviewed,
        plan_hash=plan_hash,
        entry_definition_hash=entry_definition_hash,
        exit_definition_hash=exit_definition_hash,
        entry_trace_hash=entry_trace_hash,
        exit_trace_hash=exit_trace_hash,
        compiled=compiled,
    )


def evaluate_general_research_plan(
    compiled: CompiledGeneralResearchPlan,
    market: MarketDataSet,
    *,
    initial_cash: float = 10_000.0,
) -> AcademicDevelopmentResult:
    """Regenerate from the candidate and data; never trust caller-supplied vectors."""
    _require_development_market(market)
    if (
        compiled.status != "NON_PIT_DEVELOPMENT_ONLY"
        or compiled.broker_executable
        or compiled.sealed_oos_approved
    ):
        raise GeneralResearchPlanError("research-only status integrity mismatch")
    fresh = compile_general_research_plan(compiled.plan, market)
    if fresh != compiled:
        raise GeneralResearchPlanError("compiled general plan integrity mismatch")
    return evaluate_compiled_development(fresh.compiled, market, initial_cash=initial_cash)


class GeneralPlanProvider(Protocol):
    """Opt-in structured LLM adapter; no direct operational GPT registration."""

    def propose(self, context: dict[str, Any]) -> dict[str, Any]: ...


def compile_provider_general_plan(
    provider: GeneralPlanProvider,
    market: MarketDataSet,
) -> CompiledGeneralResearchPlan:
    """Provider receives grammar+capabilities, not observations or permissions."""
    context = build_general_plan_context(market)
    try:
        response = provider.propose(deepcopy(context))
        typed = GeneralResearchPlan.model_validate(response)
    except (ValidationError, ValueError, TypeError) as exc:
        raise GeneralResearchPlanError("provider output validation failed") from exc
    return compile_general_research_plan(typed, market)
